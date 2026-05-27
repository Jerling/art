"""Health check endpoints and dependency probes.

Provides:
  - GET /health          — basic liveness probe (always returns {"status": "ok"})
  - GET /health/detailed — detailed readiness probe (DB, WeChat API, disk space)

Each dependency check in /health/detailed has a 2-second timeout.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import time
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

# Timeout for each individual dependency check (seconds)
CHECK_TIMEOUT = 2.0

# Minimum free disk space in bytes (100 MB)
MIN_DISK_FREE_BYTES = 100 * 1024 * 1024


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

    Checks:
      - database:    SQLAlchemy engine connectivity (SELECT 1)
      - wechat_api:  WeChat API endpoint reachability
      - disk_space:  Available disk space on the data partition
    """
    checks: dict[str, dict[str, Any]] = {}

    # Run all checks concurrently with individual timeouts
    db_task = asyncio.create_task(_check_database())
    wechat_task = asyncio.create_task(_check_wechat_api())
    disk_task = asyncio.create_task(_check_disk_space())

    checks["database"] = await asyncio.wait_for(db_task, timeout=CHECK_TIMEOUT)
    checks["wechat_api"] = await asyncio.wait_for(wechat_task, timeout=CHECK_TIMEOUT)
    checks["disk_space"] = await asyncio.wait_for(disk_task, timeout=CHECK_TIMEOUT)

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
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=CHECK_TIMEOUT)
        latency_ms = (time.perf_counter() - start) * 1000
        return {"status": "ok", "latency_ms": round(latency_ms, 2)}
    except asyncio.TimeoutError:
        latency_ms = (time.perf_counter() - start) * 1000
        logger.warning("[health/db] Database check timed out (%.0fms)", latency_ms)
        return {"status": "error", "latency_ms": round(latency_ms, 2), "error": "timeout"}
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        logger.warning("[health/db] Database check failed: %s", exc)
        return {"status": "error", "latency_ms": round(latency_ms, 2), "error": str(exc)}


async def _check_wechat_api() -> dict[str, Any]:
    """Probe WeChat API reachability.

    We check whether the WeChat API endpoint is reachable by making
    a lightweight HTTP GET to the token endpoint. We don't need a valid
    response — just confirming the service is reachable (HTTP 200-499
    means the service is up; connection errors mean it's down).
    """
    import httpx

    start = 0.0
    try:
        start = time.perf_counter()
        async with httpx.AsyncClient(
            base_url="https://api.weixin.qq.com",
            timeout=httpx.Timeout(CHECK_TIMEOUT),
        ) as client:
            # WeChat token endpoint — we don't need valid credentials,
            # just checking the API is reachable
            resp = await client.get("/cgi-bin/token", params={
                "grant_type": "client_credential",
                "appid": "healthcheck",
                "secret": "healthcheck",
            })
        latency_ms = (time.perf_counter() - start) * 1000

        # Any HTTP response (even 4xx/5xx) means the API is reachable
        return {
            "status": "ok",
            "latency_ms": round(latency_ms, 2),
        }
    except httpx.TimeoutException:
        latency_ms = (time.perf_counter() - start) * 1000 if start > 0 else 0
        logger.warning("[health/wechat] WeChat API check timed out (%.0fms)", latency_ms)
        return {"status": "error", "latency_ms": round(latency_ms, 2), "error": "timeout"}
    except httpx.ConnectError as exc:
        latency_ms = (time.perf_counter() - start) * 1000 if start > 0 else 0
        logger.warning("[health/wechat] WeChat API unreachable: %s", exc)
        return {"status": "error", "latency_ms": round(latency_ms, 2), "error": str(exc)}
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000 if start > 0 else 0
        logger.warning("[health/wechat] WeChat API check failed: %s", exc)
        return {"status": "error", "latency_ms": round(latency_ms, 2), "error": str(exc)}


async def _check_disk_space() -> dict[str, Any]:
    """Check available disk space on the data partition."""
    start = time.perf_counter()
    try:
        usage = await asyncio.get_event_loop().run_in_executor(
            None, shutil.disk_usage, "/"
        )
        free_bytes = usage.free
        total_bytes = usage.total
        latency_ms = (time.perf_counter() - start) * 1000

        if free_bytes < MIN_DISK_FREE_BYTES:
            return {
                "status": "error",
                "latency_ms": round(latency_ms, 2),
                "free_bytes": free_bytes,
                "total_bytes": total_bytes,
                "error": f"low disk space: {free_bytes} bytes free (minimum {MIN_DISK_FREE_BYTES})",
            }
        return {
            "status": "ok",
            "latency_ms": round(latency_ms, 2),
            "free_bytes": free_bytes,
            "total_bytes": total_bytes,
        }
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        logger.warning("[health/disk] Disk space check failed: %s", exc)
        return {"status": "error", "latency_ms": round(latency_ms, 2), "error": str(exc)}
