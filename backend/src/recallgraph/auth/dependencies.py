"""FastAPI dependencies: the authenticated user and request audit context."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from recallgraph.auth.models import User
from recallgraph.auth.service import RequestContext
from recallgraph.auth.tokens import TokenError, decode_access_token
from recallgraph.core.config import Settings
from recallgraph.db.session import get_session

_bearer = HTTPBearer(auto_error=False)


def unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def request_context(request: Request) -> RequestContext:
    request_id = getattr(request.state, "request_id", None)
    return RequestContext(
        request_id=request_id if isinstance(request_id, str) else None,
        client_ip=request.client.host if request.client else None,
    )


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise unauthorized("Missing bearer access token.")
    settings: Settings = request.app.state.settings
    try:
        user_id = decode_access_token(credentials.credentials, settings)
    except TokenError as exc:
        raise unauthorized("Invalid or expired access token.") from exc
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized("Invalid or expired access token.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
