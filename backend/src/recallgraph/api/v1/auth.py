"""Authentication endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from recallgraph.auth.dependencies import CurrentUser, request_context, unauthorized
from recallgraph.auth.schemas import (
    Credentials,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserOut,
)
from recallgraph.auth.service import (
    AuthError,
    EmailTakenError,
    RequestContext,
    TokenPair,
    login,
    logout,
    register_user,
    rotate_refresh_token,
)
from recallgraph.core.config import Settings
from recallgraph.db.session import get_session

router = APIRouter(prefix="/auth", tags=["auth"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContextDep = Annotated[RequestContext, Depends(request_context)]


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _tokens(pair: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token,
        expires_in=pair.access_expires_in,
        refresh_token=pair.refresh_token,
        refresh_expires_in=pair.refresh_expires_in,
    )


@router.post("/register", status_code=201, response_model=UserOut)
async def register(body: Credentials, session: SessionDep, ctx: ContextDep) -> UserOut:
    try:
        user = await register_user(session, body.email, body.password, ctx)
    except EmailTakenError as exc:
        raise HTTPException(status_code=409, detail="Email is already registered.") from exc
    return UserOut(id=user.id, email=user.email, created_at=user.created_at)


@router.post("/login", response_model=TokenResponse)
async def login_route(
    body: LoginRequest, request: Request, session: SessionDep, ctx: ContextDep
) -> TokenResponse:
    try:
        pair = await login(session, _settings(request), body.email, body.password, ctx)
    except AuthError as exc:
        raise unauthorized("Invalid email or password.") from exc
    return _tokens(pair)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest, request: Request, session: SessionDep, ctx: ContextDep
) -> TokenResponse:
    try:
        pair = await rotate_refresh_token(session, _settings(request), body.refresh_token, ctx)
    except AuthError as exc:
        raise unauthorized("Invalid or expired refresh token.") from exc
    return _tokens(pair)


@router.post("/logout", status_code=204)
async def logout_route(body: RefreshRequest, session: SessionDep, ctx: ContextDep) -> Response:
    await logout(session, body.refresh_token, ctx)
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut(id=user.id, email=user.email, created_at=user.created_at)
