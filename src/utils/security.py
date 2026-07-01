"""Security utilities: JWT token handling, password hashing, and FastAPI auth dependency.

FIX B1: JWT tokens expire in 24 hours (was 720h which is too long for MVP).
        secret_key is loaded from JWT_SECRET_KEY env var via config.py.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import bcrypt as _bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from .config import get_config

# NOTE: passlib 1.7.4 is incompatible with bcrypt >= 4.x (it reads
# ``bcrypt.__about__.__version__`` which was removed in bcrypt 4.1+).
# Use the bcrypt library directly — it's a thin stable API and gives us
# full control over the rounds/salt without the broken passlib wrapper.

# Cost factor for new hashes. bcrypt default is 12; keep low here only if
# the deployment machine is extremely constrained — 12 is recommended.
_BCRYPT_ROUNDS = 12

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
    except JWTError as jwt_err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from jwt_err


# ──────────────────────────────────────────────────────────────
# Password hashing
# Uses bcrypt directly because passlib 1.7.4 is incompatible with bcrypt >= 4.x.
# ──────────────────────────────────────────────────────────────
def hash_password(plain: str) -> str:
    """Return a bcrypt hash of the plain password.

    Truncates the password to 72 bytes (bcrypt's hard limit) before hashing,
    since we don't use a pre-hash wrapper. This is the same behaviour
    passlib would have given us before it broke on bcrypt 5.x.
    """
    encoded = plain.encode("utf-8")[:72]
    return _bcrypt.hashpw(encoded, _bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain password against a bcrypt hash.

    Returns False if the hash is malformed — never raises to the caller.
    """
    try:
        return _bcrypt.checkpw(
            plain.encode("utf-8")[:72],
            hashed.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


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
