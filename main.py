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
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.exceptions import HTTPException as StarletteHTTPException

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


# ── SPA fallback for extensionless deep paths ─────────────────────────────────
# vue-router uses HTML5 history mode, so a hard refresh on ``/tasks``,
# ``/login``, ``/roles`` lands on the backend as a 404 *or* a 401 (see
# below).  StaticFiles's ``html=True`` only handles *directory* fallback
# like ``/tasks/`` → ``index.html``, not extensionless bare paths like
# ``/tasks``.  Worse, ``/tasks`` / ``/roles`` / ``/messages`` ALSO match
# their respective Sprint-1 routers (``prefix="/tasks"`` etc. with
# ``Depends(require_auth)``), so a plain browser GET on those paths
# short-circuits at the auth dependency with a JSON 401 long before the
# StaticFiles mount ever sees them.
#
# The exception handlers below catch *both* 404 and 401 responses and
# return ``web/dist/index.html`` so vue-router can boot and run its own
# client-side auth guard (which reads ``art_auth_token`` from
# localStorage).  Real API / docs / metrics / health errors keep their
# JSON so ``curl``, ``authFetch``, and monitoring stay correct.
#
# Key distinguisher: when the request carries an ``Authorization``
# header it is an authenticated API call — the SPA fetches carry the
# JWT — so we MUST return JSON there.  A bare browser navigation has
# no ``Authorization`` header and gets the HTML shell.  See
# ``docs/operations/spa-fallback.md`` for the full rationale and
# verification steps.
_SPA_PREFIXES_WITH_SLASH = (
    "/api/", "/docs/", "/redoc/", "/health/", "/metrics/", "/assets/",
)
_SPA_EXACT_PATHS = frozenset({
    "/api", "/docs", "/redoc", "/health", "/metrics", "/openapi.json",
})


def _is_spa_path(request: Request, *, require_no_auth_header: bool) -> bool:
    """True if a 404/401 response for ``request`` should serve ``index.html``.

    Returns ``False`` (i.e. keep the original JSON error) when the request
    targets an API endpoint or a real static asset, AND — when
    ``require_no_auth_header`` is set — when the client sent an
    ``Authorization`` header (meaning it's an authenticated API call
    whose failure the SPA needs to see as JSON, not HTML).
    """
    path = request.url.path

    if path in _SPA_EXACT_PATHS or path.startswith(_SPA_PREFIXES_WITH_SLASH):
        return False

    last_segment = path.rsplit("/", 1)[-1]
    if "." in last_segment:
        return False

    if require_no_auth_header:
        # Authenticated API call → keep JSON error so ``authFetch`` can
        # detect the 401 and dispatch ``AUTH_EXPIRED_EVENT``.  Bare
        # browser navigation has no Authorization header.
        if request.headers.get("authorization", "").strip():
            return False

    return True


def _serve_index_html() -> Response:
    """Return ``web/dist/index.html`` (text/html) or a 404 placeholder."""
    index_path = _WEB_DIST / "index.html"
    if not index_path.is_file():
        return PlainTextResponse(
            "web/dist/index.html not built — run `cd web && npm run build`",
            status_code=404,
        )
    return FileResponse(str(index_path), media_type="text/html")


@app.exception_handler(404)
async def spa_fallback_404(request: Request, exc: StarletteHTTPException):
    """Serve ``web/dist/index.html`` for unmatched SPA deep paths.

    Excluded from fallback (return JSON 404 instead so client tooling and
    monitoring keep working):

    * ``/api/*`` — REST endpoints; 404 here means a real missing resource
    * ``/docs``, ``/redoc``, ``/openapi.json`` — FastAPI's own introspection
    * ``/metrics``, ``/health*`` — Prometheus + k8s probes
    * ``/assets/*`` — bundled static assets (falling back to ``index.html``
      would corrupt asset URLs the client expects to return binary data)
    * Anything whose last URL segment looks like a file (contains a dot),
      e.g. ``/favicon.ico`` or ``/missing.png`` — those are real asset 404s
    """
    if not _is_spa_path(request, require_no_auth_header=False):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    return _serve_index_html()


@app.exception_handler(401)
async def spa_fallback_401(request: Request, exc: StarletteHTTPException):
    """Serve ``web/dist/index.html`` for SPA deep paths blocked by ``require_auth``.

    The Sprint-1 routers (e.g. ``task_router`` with ``prefix="/tasks"``)
    attach ``Depends(require_auth)`` so a browser hard-refresh on ``/tasks``
    hits a 401 before the StaticFiles mount can fall back to ``index.html``.
    Serving the SPA shell lets ``vue-router`` run its own client-side
    guard (``isAuthenticated()`` in ``web/src/router/index.js``) and
    redirect to ``/login`` with a ``?next=`` query.

    The ``Authorization`` header check is critical: without it, the SPA's
    own ``authFetch('/tasks', ...)`` calls — which DO carry the JWT —
    would be silently rewritten to HTML and the auth-expired redirect
    handler would never fire.  See ``web/src/utils/auth.js`` for the
    AUTH_EXPIRED_EVENT contract this preserves.
    """
    if not _is_spa_path(request, require_no_auth_header=True):
        return JSONResponse(
            {"detail": "Authentication required"}, status_code=401
        )
    return _serve_index_html()


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
