import time
from contextlib import asynccontextmanager
from pathlib import Path

# Load .env FIRST so that ``DATABASE_URL``, ``JWT_SECRET_KEY`` and friends
# are populated before ``src.storage.database`` builds the engine (the
# engine reads ``DATABASE_URL`` at import time, not at first use).  We
# use ``override=False`` so anything already exported in the shell wins —
# matches the convention "12-factor app config: env first, file fallback".
try:
    from dotenv import load_dotenv

    _ENV_PATH = Path(__file__).resolve().parent / ".env"
    if _ENV_PATH.is_file():
        load_dotenv(_ENV_PATH, override=False)
except ImportError:  # pragma: no cover — python-dotenv is in pyproject deps
    pass

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from src.api.handlers.admin import router as admin_router
from src.api.handlers.auth import router as auth_router
from src.api.handlers.role import router as role_router
from src.api.handlers.role_task import role_tasks_router, task_roles_router
from src.api.handlers.task import router as task_router
from src.api.handlers.wechat import router as wechat_router
from src.api.handlers.wechat_message import router as wechat_message_router
from src.observability import metrics as _metrics  # noqa: F401 — registers Prometheus metrics
from src.observability.health import router as health_router
from src.storage.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables (idempotent for SQLite)
    import src.models  # noqa: F401
    from src.models.task import Task  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(src.models.Base.metadata.create_all)
    yield
    # Shutdown
    await engine.dispose()


app = FastAPI(title="art-agent", version="0.1.0", lifespan=lifespan)

# IMPORTANT: register /docs, /openapi.json, /redoc BEFORE adding other routes.
# FastAPI normally does this lazily during the first request, which means a
# catch-all StaticFiles mount added at startup would intercept those paths
# and return index.html.  Calling ``app.setup()`` early forces the docs
# routes into ``app.router.routes`` first so the static fallback never
# shadows them.
app.setup()

# Health check routers (mounted before other routers to ensure they always work)
app.include_router(health_router)

# Application routers
app.include_router(auth_router)
app.include_router(role_router)
app.include_router(task_router)
app.include_router(task_roles_router)
app.include_router(role_tasks_router)
app.include_router(wechat_router)
app.include_router(wechat_message_router)
app.include_router(admin_router)


# ── /metrics endpoint ─────────────────────────────────────────────────────────
# Defined here (BEFORE the StaticFiles catch-all below) so the catch-all
# doesn't shadow it.  FastAPI evaluates routes in registration order, and
# ``app.mount("/", ...)`` is greedy — anything not matched by an earlier
# route gets handed to StaticFiles, which falls back to ``index.html`` and
# returns 404 with text/html for paths that don't exist on disk.
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint.

    Exposes all registered Prometheus counters, histograms, and gauges
    in the standard Prometheus text-based exposition format.
    """
    return PlainTextResponse(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# ── Web UI (SPA) ─────────────────────────────────────────────────────────────
# Vite builds the Vue SPA into ``web/dist/``.  Mounting StaticFiles at ``/``
# with ``html=True`` makes unmatched paths fall back to ``index.html`` so
# hash-routed client routes (``/#/tasks``, ``/#/roles``) work after a hard
# refresh.  This MUST come after all API/include_router calls AND after
# ``@app.get("/metrics")`` so the routers + /metrics take priority over the
# catch-all.  See ``app.setup()`` above for the /docs ordering trick.
_WEB_DIST = Path("web/dist")
if _WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_WEB_DIST), html=True), name="web")


# ── Prometheus middleware ─────────────────────────────────────────────────────

@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    """Track request count, latency, and active connections.

    Uses a simple approach: increment active connections on entry,
    decrement on exit. Records method, endpoint path, and status code.
    """
    metrics = _metrics  # local ref for speed

    method = request.method
    metrics.http_active_connections.inc()
    start = time.perf_counter()
    status = "500"  # default if call_next raises before returning
    response: Response | None = None
    try:
        response = await call_next(request)
        status = str(response.status_code)
        return response
    finally:
        # Resolve the matched route template AFTER call_next so we never use
        # the raw path as a label (which would create unbounded cardinality
        # for /tasks/{id} style paths and OOM Prometheus on traffic).
        route = request.scope.get("route")
        endpoint = getattr(route, "path", None) or "__unmatched__"
        elapsed = time.perf_counter() - start
        metrics.http_requests_total.labels(
            method=method, endpoint=endpoint, status=status
        ).inc()
        metrics.http_request_duration_seconds.labels(
            method=method, endpoint=endpoint
        ).observe(elapsed)
        metrics.http_active_connections.dec()


# ── Metrics endpoint ──────────────────────────────────────────────────────────
# NOTE: ``/metrics`` is registered ABOVE (before the StaticFiles catch-all)
# so it isn't shadowed by the SPA fallback.  See the comment block above
# the StaticFiles mount for the ordering rationale.  This trailing block
# was kept for history; the handler itself was removed by the Sprint 4
# 收尾 fix (task t_0e04abde).
