"""JWT auth login endpoint.

Sprint 4 收尾 — closes the functional gap from ``require_auth`` (commit b2e30a1):
without a login endpoint, every protected API returns 401 and the Web UI
cannot acquire a token.

Endpoints:
- ``POST /api/v1/auth/login`` — username + password → JWT
- ``GET  /api/v1/auth/me``    — introspection: returns the current user
                                (useful for the Web UI to check the token
                                is still valid and to render the username)
"""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User
from src.schemas.auth import CurrentUser, LoginRequest, TokenResponse
from src.storage.database import get_session
from src.utils.config import get_config
from src.utils.security import create_access_token, require_auth, verify_password

logger = logging.getLogger(__name__)

# This router is intentionally NOT protected — login must be reachable
# without a token.  Everything else (roles, tasks, messages, admin) is
# already gated by ``Depends(require_auth)`` at the router level.
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(
    data: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Authenticate a user and issue a JWT access token.

    On invalid credentials we return ``401`` with a generic message —
    never disclose whether the username exists.
    """
    result = await session.execute(
        select(User).where(User.username == data.username)
    )
    user: User | None = result.scalar_one_or_none()

    # Always run verify_password (with a dummy hash when user is missing)
    # to avoid a username-enumeration timing side-channel.
    if user is None:
        # burn a comparable amount of CPU so timing doesn't leak existence
        verify_password(data.password, "$2b$12$" + "x" * 53)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    cfg = get_config()
    expires_seconds = cfg.auth.jwt_expire_hours * 3600
    token = create_access_token(
        {
            "sub": user.username,
            "uid": user.id,
            "adm": user.is_admin,
        }
    )

    logger.info("[auth_login] user=%s id=%d issued token (ttl=%ds)", user.username, user.id, expires_seconds)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_seconds,
    )


@router.get(
    "/me",
    response_model=CurrentUser,
    dependencies=[Depends(require_auth)],
)
async def get_me(
    payload: Annotated[dict[str, Any], Depends(require_auth)],
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    """Return the currently authenticated user (introspection endpoint)."""
    user_id = payload.get("uid")
    if not isinstance(user_id, int):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user identity",
        )
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
        )
    return CurrentUser(id=user.id, username=user.username, is_admin=user.is_admin)
