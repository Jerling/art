"""Pydantic schemas for JWT auth login.

Sprint 4 收尾 — minimal request/response shapes for ``POST /api/v1/auth/login``.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Body of ``POST /api/v1/auth/login``."""

    username: str = Field(..., min_length=1, max_length=64, description="Login username")
    password: str = Field(..., min_length=1, max_length=128, description="Login password")


class TokenResponse(BaseModel):
    """Response body for a successful login."""

    access_token: str = Field(..., description="Signed JWT access token")
    token_type: str = Field(default="bearer", description="Token type — always 'bearer'")
    expires_in: int = Field(..., description="Token lifetime in seconds")


class CurrentUser(BaseModel):
    """Minimal current-user info returned by ``GET /api/v1/auth/me``."""

    id: int
    username: str
    is_admin: bool
