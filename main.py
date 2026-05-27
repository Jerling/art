from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

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
    async with engine.begin() as conn:
        # Import all models so SQLAlchemy metadata picks them up
        import src.models  # noqa: F401
        from src.models.task import Task  # noqa: F401
    yield
    # Shutdown
    await engine.dispose()


app = FastAPI(title="art-agent", version="0.1.0", lifespan=lifespan)

# Health check routers (mounted before other routers to ensure they always work)
app.include_router(health_router)

# Application routers
app.include_router(role_router)
app.include_router(task_router)
app.include_router(task_roles_router)
app.include_router(role_tasks_router)
app.include_router(wechat_router)
app.include_router(wechat_message_router)


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint.

    Exposes all registered Prometheus counters and histograms
    in the standard Prometheus text-based exposition format.
    """
    return PlainTextResponse(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
