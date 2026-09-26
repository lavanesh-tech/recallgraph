"""Registration, login, refresh-token rotation with reuse detection, logout, auditing."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from recallgraph.auth.models import AuditEvent, RefreshToken, User
from recallgraph.auth.passwords import (
    burn_verification,
    hash_password,
    needs_rehash,
    verify_password,
)
from recallgraph.auth.tokens import create_access_token, hash_refresh_token, new_refresh_token
from recallgraph.core.config import Settings


class AuthError(Exception):
    """Authentication failed. The reason is audited, never returned to the client."""


class EmailTakenError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: str | None
    client_ip: str | None


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    access_expires_in: int
    refresh_token: str
    refresh_expires_in: int


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _audit(
    session: AsyncSession,
    event: str,
    ctx: RequestContext,
    *,
    user_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEvent(
            event=event,
            user_id=user_id,
            request_id=ctx.request_id,
            client_ip=ctx.client_ip,
            details=details or {},
        )
    )


async def register_user(
    session: AsyncSession, email: str, password: str, ctx: RequestContext
) -> User:
    user = User(email=normalize_email(email), password_hash=hash_password(password))
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        _audit(session, "register_rejected", ctx, details={"reason": "email_taken"})
        await session.commit()
        raise EmailTakenError from exc
    _audit(session, "register", ctx, user_id=user.id)
    await session.commit()
    return user


async def _issue(
    session: AsyncSession, user: User, settings: Settings, family_id: uuid.UUID
) -> tuple[TokenPair, uuid.UUID]:
    raw, digest = new_refresh_token()
    now = datetime.now(UTC)
    token = RefreshToken(
        user_id=user.id,
        family_id=family_id,
        token_hash=digest,
        issued_at=now,
        expires_at=now + timedelta(seconds=settings.refresh_token_ttl_s),
    )
    session.add(token)
    await session.flush()
    access, ttl = create_access_token(user.id, settings, now=now)
    return TokenPair(access, ttl, raw, settings.refresh_token_ttl_s), token.id


async def login(
    session: AsyncSession, settings: Settings, email: str, password: str, ctx: RequestContext
) -> TokenPair:
    user = await session.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        burn_verification(password)  # same cost as a real check: no user-enumeration timing
        ok = False
    else:
        ok = verify_password(user.password_hash, password) and user.is_active
    if not ok or user is None:
        reason = "unknown_email" if user is None else "bad_password_or_inactive"
        _audit(
            session,
            "login_failure",
            ctx,
            user_id=user.id if user else None,
            details={"reason": reason},
        )
        await session.commit()
        raise AuthError(reason)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = datetime.now(UTC)
    pair, _ = await _issue(session, user, settings, uuid.uuid4())
    _audit(session, "login_success", ctx, user_id=user.id)
    await session.commit()
    return pair


async def rotate_refresh_token(
    session: AsyncSession, settings: Settings, raw: str, ctx: RequestContext
) -> TokenPair:
    """One-time-use refresh tokens. Presenting an already-used token revokes the whole family
    (the token was probably stolen), forcing a fresh login."""
    now = datetime.now(UTC)
    token = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(raw))
        .with_for_update()
    )
    if token is None:
        _audit(session, "refresh_failure", ctx, details={"reason": "unknown_token"})
        await session.commit()
        raise AuthError("unknown_token")
    if token.revoked_at is not None:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == token.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        _audit(
            session,
            "refresh_reuse_detected",
            ctx,
            user_id=token.user_id,
            details={"family_id": str(token.family_id)},
        )
        await session.commit()
        raise AuthError("reuse_detected")
    user = await session.get(User, token.user_id)
    if token.expires_at <= now or user is None or not user.is_active:
        _audit(
            session, "refresh_failure", ctx, user_id=token.user_id, details={"reason": "expired"}
        )
        await session.commit()
        raise AuthError("expired_or_inactive")
    token.revoked_at = now
    pair, new_id = await _issue(session, user, settings, token.family_id)
    token.replaced_by_id = new_id
    _audit(session, "refresh", ctx, user_id=user.id)
    await session.commit()
    return pair


async def logout(session: AsyncSession, raw: str, ctx: RequestContext) -> None:
    """Revokes the token's whole family (this login session). Idempotent, reveals nothing."""
    token = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw))
    )
    if token is not None:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == token.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        _audit(session, "logout", ctx, user_id=token.user_id)
        await session.commit()
