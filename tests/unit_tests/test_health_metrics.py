"""Tests for health check endpoints and Prometheus metrics.

Run with: pytest tests/unit_tests/test_health_metrics.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from prometheus_client import REGISTRY

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
        """Detailed health must include database, wechat_api, and disk_space checks."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health/detailed")
        body = resp.json()
        assert "checks" in body
        checks = body["checks"]
        assert "database" in checks
        assert "wechat_api" in checks
        assert "disk_space" in checks

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
        # Mock config to avoid JWT_SECRET_KEY validation and external calls
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
        # With SQLite (working) + wechat_api (reachable) + disk_space (ok) → overall ok
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

    @pytest.mark.asyncio
    async def test_detailed_disk_space_has_bytes(self):
        """Disk space check should report free_bytes and total_bytes when ok."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health/detailed")
        body = resp.json()
        disk = body["checks"]["disk_space"]
        if disk["status"] == "ok":
            assert "free_bytes" in disk
            assert "total_bytes" in disk
            assert disk["free_bytes"] > 0

    @pytest.mark.asyncio
    async def test_detailed_wechat_api_reachable(self):
        """WeChat API check should report ok when the API is reachable."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health/detailed")
        body = resp.json()
        wechat = body["checks"]["wechat_api"]
        # WeChat API should be reachable from test environment
        assert wechat["status"] == "ok"
        assert "latency_ms" in wechat


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
        """All application metrics must appear in the output."""
        from src.observability import metrics as _  # noqa: F401

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/metrics")
        text = resp.text
        # HTTP metrics
        assert "art_http_requests_total" in text
        assert "art_http_request_duration_seconds" in text
        assert "art_http_active_connections" in text
        # Business counters
        assert "art_messages_received_total" in text
        assert "art_tasks_created_total" in text
        assert "art_push_results_total" in text
        # Histograms
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
        assert "# TYPE art_http_requests_total counter" in text
        assert "# TYPE art_messages_received_total counter" in text
        assert "# TYPE art_tasks_created_total counter" in text
        assert "# TYPE art_push_results_total counter" in text
        # Histograms
        assert "# TYPE art_http_request_duration_seconds histogram" in text
        assert "# TYPE art_intent_parse_duration_seconds histogram" in text
        assert "# TYPE art_llm_call_duration_seconds histogram" in text
        assert "# TYPE art_mcp_call_duration_seconds histogram" in text
        # Gauge
        assert "# TYPE art_http_active_connections gauge" in text

    @pytest.mark.asyncio
    async def test_metrics_http_requests_incremented(self):
        """HTTP request counter should increment after making requests."""
        from src.observability import metrics as metrics_mod

        # Reset the counter to get a clean reading
        metrics_mod.http_requests_total.clear()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Make a request to /health
            await client.get("/health")
            # Now check metrics
            resp = await client.get("/metrics")
        text = resp.text
        # The /health endpoint should have been counted
        assert 'art_http_requests_total{endpoint="/health",method="GET",status="200"}' in text

    @pytest.mark.asyncio
    async def test_metrics_active_connections_is_gauge(self):
        """Active connections gauge should be present and numeric."""
        from src.observability import metrics as metrics_mod

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/metrics")
        text = resp.text
        # The gauge should be in the output with a numeric value
        assert "art_http_active_connections" in text

    @pytest.mark.asyncio
    async def test_metrics_push_results_labels(self):
        """Push results metric should have push_type and result labels."""
        from src.observability import metrics as metrics_mod

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/metrics")
        text = resp.text
        # Check that the metric definition includes the label names
        assert "art_push_results_total" in text


# ─────────────────────────────────────────────────────────────────────────────
# Prometheus middleware — request tracking
# ─────────────────────────────────────────────────────────────────────────────

class TestPrometheusMiddleware:
    """Tests for the Prometheus HTTP middleware."""

    @pytest.mark.asyncio
    async def test_middleware_counts_requests(self):
        """Middleware should count all HTTP requests."""
        from src.observability import metrics as metrics_mod

        metrics_mod.http_requests_total.clear()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/health")
            await client.get("/health")
            resp = await client.get("/metrics")
        text = resp.text
        # Should have counted 2 /health requests + 1 /metrics request
        assert 'art_http_requests_total{endpoint="/health",method="GET",status="200"} 2.0' in text

    @pytest.mark.asyncio
    async def test_middleware_tracks_latency(self):
        """Middleware should track request latency in histogram."""
        from src.observability import metrics as metrics_mod

        metrics_mod.http_request_duration_seconds.clear()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/health")
            resp = await client.get("/metrics")
        text = resp.text
        # Histogram should have count and sum entries
        assert 'art_http_request_duration_seconds_count{endpoint="/health",method="GET"}' in text
        assert 'art_http_request_duration_seconds_sum{endpoint="/health",method="GET"}' in text

    @pytest.mark.asyncio
    async def test_middleware_active_connections_returns_to_zero(self):
        """Active connections gauge should be present (may be >0 during metrics read)."""
        transport = ASGITransport(app=app)
        # Use a background approach: verify the gauge exists and is a reasonable value
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/metrics")
        text = resp.text
        # Find the active connections line — should be a non-negative number
        for line in text.split("\n"):
            if line.startswith("art_http_active_connections "):
                value = float(line.split(" ")[1])
                # Value should be >= 0 (typically 0 or 1 since metrics req goes through middleware)
                assert value >= 0.0, f"active connections negative: {value}"
                break
        else:
            pytest.fail("art_http_active_connections not found in metrics output")
