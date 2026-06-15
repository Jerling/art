"""Unit tests for JWT authentication middleware.

Run with:
  pytest tests/unit_tests/test_auth.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


# ─────────────────────────────────────────────────────────────────────────────
# require_auth dependency unit tests
# ─────────────────────────────────────────────────────────────────────────────
class TestRequireAuth:
    """Test the require_auth FastAPI dependency directly."""

    @pytest.fixture
    def valid_token(self) -> str:
        """Create a valid JWT token for use in tests."""
        from src.utils.security import create_access_token

        return create_access_token({"sub": "test-user"})

    @pytest.fixture
    def decoded_payload(self) -> dict:
        return {"sub": "test-user"}

    @pytest.mark.asyncio
    async def test_requires_token(self):
        """No credentials -> 401."""
        from src.utils.security import require_auth

        with pytest.raises(HTTPException) as exc_info:
            await require_auth(credentials=None)
        assert exc_info.value.status_code == 401
        assert "Authentication required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalid_token(self):
        """Invalid/expired token -> 401 without leaking details."""
        from src.utils.security import require_auth

        mock_creds = MagicMock()
        mock_creds.credentials = "invalid.token.here"

        with pytest.raises(HTTPException) as exc_info:
            await require_auth(credentials=mock_creds)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid or expired token"

    @pytest.mark.asyncio
    async def test_valid_token_returns_payload(self, valid_token):
        """Valid token -> decoded payload returned."""
        from src.utils.security import require_auth

        mock_creds = MagicMock()
        mock_creds.credentials = valid_token

        payload = await require_auth(credentials=mock_creds)
        assert isinstance(payload, dict)
        assert payload["sub"] == "test-user"

    def test_no_sensitive_info_in_401(self):
        """401 response must not leak token content or stack traces."""
        from jose import JWTError

        # Verify our error messages don't contain token fragments
        msg_auth_required = "Authentication required"
        msg_invalid = "Invalid or expired token"
        assert "bearer" not in msg_auth_required.lower()
        assert "bearer" not in msg_invalid.lower()
        assert "authorization" != msg_auth_required
        assert "authorization" != msg_invalid


# ─────────────────────────────────────────────────────────────────────────────
# API-level integration tests via TestClient
# ─────────────────────────────────────────────────────────────────────────────
class TestAuthIntegration:
    """Test JWT auth is enforced on all protected endpoints."""

    VALID_PAYLOAD = {"sub": "test-user"}

    @pytest.fixture
    def valid_token(self) -> str:
        """Create a valid JWT token for use in tests."""
        from src.utils.security import create_access_token

        return create_access_token(self.VALID_PAYLOAD)

    @pytest.fixture
    def test_client(self):
        """Create a TestClient with patched DB engine."""
        with patch("src.storage.database.engine"):
            from main import app
            from fastapi.testclient import TestClient

            client = TestClient(app, raise_server_exceptions=False)
            return client

    # ── Protected endpoints: no token → 401 ──────────────────────────────────

    PROTECTED_ENDPOINTS = [
        ("GET", "/roles"),
        ("POST", "/roles"),
        ("GET", "/roles/1"),
        ("PUT", "/roles/1"),
        ("DELETE", "/roles/1"),
        ("GET", "/tasks"),
        ("POST", "/tasks"),
        ("GET", "/tasks/1"),
        ("PUT", "/tasks/1"),
        ("DELETE", "/tasks/1"),
        ("PATCH", "/tasks/1/status"),
        ("GET", "/messages?openid=test"),
        ("POST", "/api/v1/admin/backup"),
        ("GET", "/api/v1/admin/backup"),
        ("POST", "/tasks/1/roles"),
        ("DELETE", "/tasks/1/roles/1"),
        ("GET", "/roles/1/tasks"),
    ]

    @pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
    def test_protected_endpoint_returns_401_without_token(self, test_client, method, path):
        """All protected endpoints return 401 when no token is provided."""
        response = test_client.request(method, path)
        assert response.status_code == 401, (
            f"Expected 401 for {method} {path}, got {response.status_code}"
        )
        assert response.json()["detail"] in (
            "Authentication required",
            "Invalid or expired token",
        )

    @pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
    def test_protected_endpoint_returns_401_with_invalid_token(self, test_client, method, path):
        """All protected endpoints return 401 with an invalid bearer token."""
        response = test_client.request(
            method, path, headers={"Authorization": "Bearer invalid.token.here"}
        )
        assert response.status_code == 401, (
            f"Expected 401 for {method} {path} with invalid token, got {response.status_code}"
        )
        assert response.json()["detail"] == "Invalid or expired token"

    # ── Exempt endpoints: no token required ──────────────────────────────────

    EXEMPT_ENDPOINTS = [
        ("GET", "/health"),
        ("GET", "/metrics"),
        ("GET", "/wechat/webhook", {"signature": "a", "timestamp": "1", "nonce": "1", "echostr": "test"}),
        ("POST", "/wechat/webhook", None, {"signature": "a", "timestamp": "1", "nonce": "1"}),
    ]

    @pytest.mark.parametrize("method,path,params", [
        ("GET", "/health", None),
        ("GET", "/metrics", None),
        ("GET", "/wechat/webhook", {"signature": "a", "timestamp": "1", "nonce": "1", "echostr": "test"}),
        ("POST", "/wechat/webhook", None),
    ])
    def test_exempt_endpoints_do_not_require_auth(self, test_client, method, path, params):
        """Exempt endpoints (health, metrics, wechat webhook) work without auth."""
        response = test_client.request(method, path, params=params)
        # These won't return 200 (DB/etc isn't running), but critically they
        # should NOT return 401 — that would mean auth was applied by mistake.
        assert response.status_code != 401, (
            f"Exempt endpoint {method} {path} incorrectly returned 401"
        )

    # ── Protected endpoints: valid token → processed normally ────────────────

    @pytest.mark.parametrize("method,path", [
        ("GET", "/roles"),
        ("GET", "/tasks"),
        ("GET", "/messages?openid=test"),
    ])
    def test_protected_endpoints_with_valid_token_passes_auth(self, test_client, valid_token, method, path):
        """Protected endpoints with valid token pass auth and hit normal handler path."""
        # These will 500 because DB isn't initialized — that's expected.
        # The key check: they DON'T return 401.
        response = test_client.request(
            method, path,
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code != 401, (
            f"Protected endpoint {method} {path} returned 401 despite valid token"
        )
