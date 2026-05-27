"""Health check endpoints and dependency probes.

Provides:
  - GET /health          — basic liveness probe (always returns {"status": "ok"})
  - GET /health/detailed — detailed readiness probe (DB, Redis, LLM availability)
"""
from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


# ── Liveness ──────────────────────────────────────────────────────────────────


@router.get("/health")
async def health() -> dict[str, str]:
    """Basic liveness probe.

    Returns 200 OK as long as the process is running.
    No dependency checks are performed.
    """
    return {"status": "ok"}


# ── Readiness / Detailed Health ───────────────────────────────────────────────


@router.get("/health/detailed")
async def health_detailed() -> dict[str, Any]:
    """Detailed readiness probe.

    Checks each downstream dependency and reports its status.
    Returns 200 if all dependencies are healthy, 503 otherwise.
    """
    checks: dict[str, dict[str, Any]] = {}

    checks["database"] = await _check_database()
    checks["redis"] = await _check_redis()
    checks["llm"] = await _check_llm()

    overall = "ok" if all(c.get("status") == "ok" for c in checks.values()) else "degraded"

    return {
        "status": overall,
        "checks": checks,
    }


# ── Dependency probes ─────────────────────────────────────────────────────────


async def _check_database() -> dict[str, Any]:
    """Probe the database by executing a simple SELECT 1."""
    from sqlalchemy import text

    from src.storage.database import engine

    start = time.perf_counter()
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        latency_ms = (time.perf_counter() - start) * 1000
        return {"status": "ok", "latency_ms": round(latency_ms, 2)}
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        logger.warning("[health/db] Database check failed: %s", exc)
        return {"status": "error", "latency_ms": round(latency_ms, 2), "error": str(exc)}


async def _check_redis() -> dict[str, Any]:
    """Probe Redis by sending PING."""
    try:
        import redis.asyncio as redis
    except ImportError:
        return {"status": "error", "error": "redis package not installed"}

    start = 0.0
    try:
        from src.utils.config import get_config

        config = get_config()
        redis_url = config.redis.url if config.redis else None
        if not redis_url:
            return {"status": "ok", "detail": "redis not configured — skipped"}

        start = time.perf_counter()
        r = redis.from_url(redis_url, socket_timeout=5)
        try:
            await r.ping()
            latency_ms = (time.perf_counter() - start) * 1000
            return {"status": "ok", "latency_ms": round(latency_ms, 2)}
        finally:
            await r.aclose()
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000 if start > 0 else 0
        logger.warning("[health/redis] Redis check failed: %s", exc)
        return {"status": "error", "latency_ms": round(latency_ms, 2), "error": str(exc)}


async def _check_llm() -> dict[str, Any]:
    """Probe LLM provider availability via a lightweight API call.

    We check whether the configured LLM provider has a valid API key
    and can reach the API endpoint. We do NOT make a full completion
    request — just verify the endpoint is reachable (HTTP 200 or 401/403
    both mean the service is up; only connection errors mean it's down).
    """
    import httpx

    from src.utils.config import get_config

    start = 0.0
    try:
        from src.utils.config import get_config

        config = get_config()
        provider_name = config.llm_provider or "glm"

        if provider_name == "minimax":
            from src.llm.minimax import MiniMaxProvider

            provider_cfg = config.minimax
            base_url = MiniMaxProvider.DEFAULT_BASE_URL
            api_key = provider_cfg.api_key if provider_cfg else None
        else:
            from src.llm.glm import GLMProvider

            provider_cfg = config.glm
            base_url = GLMProvider.DEFAULT_BASE_URL
            api_key = provider_cfg.api_key if provider_cfg else None

        if not api_key:
            return {"status": "ok", "detail": f"{provider_name} API key not set — skipped"}

        start = time.perf_counter()
        async with httpx.AsyncClient(base_url=base_url, timeout=httpx.Timeout(5.0)) as client:
            resp = await client.get(
                "/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        latency_ms = (time.perf_counter() - start) * 1000

        if resp.status_code in (200, 401, 403):
            return {
                "status": "ok",
                "provider": provider_name,
                "latency_ms": round(latency_ms, 2),
            }
        return {
            "status": "error",
            "provider": provider_name,
            "latency_ms": round(latency_ms, 2),
            "error": f"unexpected status {resp.status_code}",
        }
    except httpx.ConnectError as exc:
        latency_ms = (time.perf_counter() - start) * 1000 if start > 0 else 0
        logger.warning("[health/llm] LLM provider unreachable: %s", exc)
        return {"status": "error", "latency_ms": round(latency_ms, 2), "error": str(exc)}
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000 if start > 0 else 0
        logger.warning("[health/llm] LLM check failed: %s", exc)
        return {"status": "error", "latency_ms": round(latency_ms, 2), "error": str(exc)}
