"""Security utilities: JWT token handling, password hashing, and FastAPI auth dependency.

FIX B1: JWT tokens expire in 24 hours (was 720h which is too long for MVP).
        secret_key is loaded from JWT_SECRET_KEY env var via config.py.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import get_config

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── JWT auth dependency ─────────────────────────────────────────────────────────

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
) -> dict[str, Any]:
    """FastAPI dependency: verify JWT bearer token on protected endpoints.

    Extracts the token from the ``Authorization: Bearer <token>`` header,
    decodes and validates it via :func:`decode_access_token`.

    Returns
    -------
    dict[str, Any]
        The decoded token payload (e.g. ``{"sub": "user_id", ...}``) so
        handlers can inspect caller identity if needed.

    Raises
    ------
    HTTPException 401
        Generic error — never reveals token content or stack traces.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(credentials.credentials)
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ──────────────────────────────────────────────────────────────
# Password hashing
# ──────────────────────────────────────────────────────────────
def hash_password(plain: str) -> str:
    """Return a bcrypt hash of the plain password."""
    return pwd_context.hash(plain)  # type: ignore[no-any-return]


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain password against a bcrypt hash."""
    return pwd_context.verify(plain, hashed)  # type: ignore[no-any-return]


# ──────────────────────────────────────────────────────────────
# JWT tokens — FIX B1: 24h expiry (was 720h)
# ──────────────────────────────────────────────────────────────
def create_access_token(data: dict[str, Any], *, expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT access token.

    FIX B1: Default expiry is 24 hours. The 720h (30-day) expiry was too long
    for MVP where tokens should be short-lived.
    """
    cfg = get_config()
    to_encode = data.copy()

    expire_hours = cfg.auth.jwt_expire_hours  # Default 24h (set in config)
    if expires_delta is not None:
        expire_hours = int(expires_delta.total_seconds() / 3600)

    expire = datetime.now(UTC) + timedelta(hours=expire_hours)
    to_encode |= {"exp": expire, "iat": datetime.now(UTC)}

    return jwt.encode(  # type: ignore[no-any-return]
        to_encode,
        cfg.auth.secret_key,
        algorithm=cfg.auth.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT token. Raises JWTError on failure."""
    cfg = get_config()
    return jwt.decode(  # type: ignore[no-any-return]
        token,
        cfg.auth.secret_key,
        algorithms=[cfg.auth.jwt_algorithm],
    )


def verify_token(token: str) -> bool:
    """Return True if token is valid and not expired, False otherwise."""
    try:
        decode_access_token(token)
        return True
    except JWTError:
        return False
