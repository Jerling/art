"""Configuration loading with environment variable injection.

FIX B1: JWT secret_key loaded from JWT_SECRET_KEY env var (not hardcoded).
FIX B2: Redis URL uses standard format redis://user:***@host:port/db.
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ──────────────────────────────────────────────────────────────
# AuthConfig — JWT settings
# FIX B1: secret_key MUST be provided via JWT_SECRET_KEY env var.
#         Token expiry is 24 hours (was incorrectly 720h).
# ──────────────────────────────────────────────────────────────
class AuthConfig(BaseModel):
    secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = Field(default=24, description="JWT token validity in hours. Default 24h.")

    @model_validator(mode="after")
    def _require_secret_key(self) -> AuthConfig:
        if not self.secret_key:
            secret = os.environ.get("JWT_SECRET_KEY", "")
            if not secret:
                raise ValueError(
                    "JWT_SECRET_KEY environment variable must be set. "
                    "Generate one with: python -c \"from secrets import token_urlsafe; print(token_urlsafe(32))\""
                )
            self.secret_key = secret
        elif self.secret_key == "your-secret-key-here":
            # Still being used as placeholder — try env var
            secret = os.environ.get("JWT_SECRET_KEY", "")
            if not secret:
                raise ValueError(
                    "JWT_SECRET_KEY environment variable must be set. "
                    "Remove 'your-secret-key-here' placeholder and set a real secret."
                )
            self.secret_key = secret
        return self


# ──────────────────────────────────────────────────────────────
# RedisConfig — FIX B2: standard redis:// URL format
# The non-standard 'redis**:*@' syntax is rejected.
# ──────────────────────────────────────────────────────────────
class RedisConfig(BaseModel):
    url: str = "redis://localhost:6379/0"

    @field_validator("url", mode="before")
    @classmethod
    def _validate_url_format(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError(f"Redis URL must be a string, got {type(v).__name__}")
        if "***@" in v or "@@" in v:
            raise ValueError(
                f"Non-standard Redis URL syntax detected: {v!r}. "
                "Use format: redis://user**:*@host:port/db"
            )
        if not (v.startswith("redis://") or v.startswith("rediss://")):
            raise ValueError(
                f"Invalid Redis URL scheme: {v!r}. Must start with redis:// or rediss://"
            )
        return v


# ──────────────────────────────────────────────────────────────
# Supporting config models
# ──────────────────────────────────────────────────────────────
class DatabaseConfig(BaseModel):
    host: str = "localhost"
    port: int = 5432
    name: str = "art"
    user: str = "postgres"
    password: str = ""


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000


class LLMProviderConfig(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = ""


class WeChatConfig(BaseModel):
    app_id: str = ""
    app_secret: str = ""


class OpenVikingMCPConfig(BaseModel):
    url: str = ""


# ──────────────────────────────────────────────────────────────
# Main application config
# ──────────────────────────────────────────────────────────────
class AppConfig(BaseSettings):
    """Main application configuration."""

    model_config = SettingsConfigDict(
        env_prefix="ART_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    server: ServerConfig = Field(default_factory=ServerConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    llm_provider: str = "glm"
    minimax: LLMProviderConfig | None = None
    glm: LLMProviderConfig | None = None
    openai: LLMProviderConfig | None = None
    anthropic: LLMProviderConfig | None = None
    ollama: LLMProviderConfig | None = None
    wechat: WeChatConfig = Field(default_factory=WeChatConfig)
    open_viking: OpenVikingMCPConfig = Field(default_factory=OpenVikingMCPConfig)

    @classmethod
    def load_from_file(cls, path: str | Path = "config.json") -> AppConfig:
        """Load config from a JSON file, merging with env var overrides."""
        import json

        config_path = Path(path)
        if config_path.exists():
            with open(config_path) as f:
                data = json.load(f)
            return cls(**data)
        return cls()


# ──────────────────────────────────────────────────────────────
# Module-level singleton accessor
# ──────────────────────────────────────────────────────────────
_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Return the cached application config singleton."""
    global _config
    if _config is None:
        _config = AppConfig.load_from_file()
    return _config
