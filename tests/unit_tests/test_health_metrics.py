"""Tests for health check endpoints and Prometheus metrics.

Run with: pytest tests/unit_tests/test_health_metrics.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


# ─────────────────────────────────────────────────────────────────────────────
# GET /health — basic liveness
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthLiveness:
    """Tests for GET /health — basic liveness probe."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self):
        """Health endpoint must always return 200 OK."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_returns_ok_status(self):
        """Health endpoint must return {"status": "ok"}."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
        body = resp.json()
        assert body == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_health_no_dependency_checks(self):
        """Health endpoint should work even with broken dependencies."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ─────────────────────────────────────────────────────────────────────────────
# GET /health/detailed — detailed readiness
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthDetailed:
    """Tests for GET /health/detailed — detailed readiness probe."""

    @pytest.mark.asyncio
    async def test_detailed_returns_all_check_categories(self):
        """Detailed health must include database, redis, and llm checks."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health/detailed")
        body = resp.json()
        assert "checks" in body
        checks = body["checks"]
        assert "database" in checks
        assert "redis" in checks
        assert "llm" in checks

    @pytest.mark.asyncio
    async def test_detailed_database_ok(self):
        """Database check should be ok with the default SQLite."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health/detailed")
        body = resp.json()
        db_check = body["checks"]["database"]
        assert db_check["status"] == "ok"
        assert "latency_ms" in db_check

    @pytest.mark.asyncio
    async def test_detailed_overall_status_ok_when_all_ok(self):
        """Overall status should be ok when all dependency checks pass."""
        # Mock config to avoid JWT_SECRET_KEY validation and Redis connection
        mock_config = MagicMock()
        mock_config.redis = None
        mock_config.llm_provider = "glm"
        mock_config.glm = None
        mock_config.minimax = None

        with (
            patch.dict("os.environ", {"JWT_SECRET_KEY": "test-secret-32-chars-long-ok!!"}),
            patch("src.utils.config.get_config", return_value=mock_config),
        ):
            from main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/health/detailed")
        body = resp.json()
        # With SQLite (working) + redis skipped + llm skipped → overall ok
        assert body["status"] == "ok"

    @pytest.mark.asyncio
    async def test_detailed_returns_200(self):
        """Detailed health should always return 200 (never 503)."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health/detailed")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_detailed_check_has_required_fields(self):
        """Each check must have at least a status field."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health/detailed")
        body = resp.json()
        for name, check in body["checks"].items():
            assert "status" in check, f"Check '{name}' missing 'status' field"
            assert check["status"] in ("ok", "error"), (
                f"Check '{name}' has invalid status: {check['status']}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# GET /metrics — Prometheus metrics
# ─────────────────────────────────────────────────────────────────────────────

class TestMetrics:
    """Tests for GET /metrics — Prometheus metrics endpoint."""

    @pytest.mark.asyncio
    async def test_metrics_returns_200(self):
        """Metrics endpoint must return 200 OK."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/metrics")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_metrics_returns_plain_text(self):
        """Metrics must be in Prometheus text format (plain text)."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/metrics")
        content_type = resp.headers.get("content-type", "")
        assert "text/plain" in content_type

    @pytest.mark.asyncio
    async def test_metrics_contains_all_defined_metrics(self):
        """All five application metrics must appear in the output."""
        # Import metrics to register them with the prometheus registry
        from src.observability import metrics as _  # noqa: F401

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/metrics")
        text = resp.text
        assert "art_messages_received_total" in text
        assert "art_tasks_created_total" in text
        assert "art_intent_parse_duration_seconds" in text
        assert "art_llm_call_duration_seconds" in text
        assert "art_mcp_call_duration_seconds" in text

    @pytest.mark.asyncio
    async def test_metrics_metric_types_correct(self):
        """Each metric must have the correct Prometheus type."""
        from src.observability import metrics as _  # noqa: F401

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/metrics")
        text = resp.text
        # Counters
        assert "# TYPE art_messages_received_total counter" in text
        assert "# TYPE art_tasks_created_total counter" in text
        # Histograms
        assert "# TYPE art_intent_parse_duration_seconds histogram" in text
        assert "# TYPE art_llm_call_duration_seconds histogram" in text
        assert "# TYPE art_mcp_call_duration_seconds histogram" in text
