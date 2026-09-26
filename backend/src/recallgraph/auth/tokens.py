"""Short-lived JWT access tokens and opaque, hashed-at-rest refresh tokens."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from recallgraph.core.config import Settings

ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"  # noqa: S105 - JWT "typ" claim value


class TokenError(Exception):
    """An access token is missing, malformed, expired or otherwise invalid."""


def create_access_token(
    user_id: uuid.UUID,
    settings: Settings,
    *,
    now: datetime | None = None,
    ttl_s: int | None = None,
) -> tuple[str, int]:
    issued = now or datetime.now(UTC)
    ttl = settings.access_token_ttl_s if ttl_s is None else ttl_s
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": issued,
        "exp": issued + timedelta(seconds=ttl),
        "jti": uuid.uuid4().hex,
        "typ": ACCESS_TOKEN_TYPE,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)
    return token, ttl


def decode_access_token(token: str, settings: Settings) -> uuid.UUID:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],  # never trust the token's own "alg" header
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "jti", "iss", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(type(exc).__name__) from exc
    if claims.get("typ") != ACCESS_TOKEN_TYPE:
        raise TokenError("wrong token type")
    try:
        return uuid.UUID(str(claims["sub"]))
    except ValueError as exc:
        raise TokenError("invalid subject") from exc


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_refresh_token() -> tuple[str, str]:
    """(raw token for the client, SHA-256 digest for the database)."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_refresh_token(raw)
