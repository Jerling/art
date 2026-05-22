from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.handlers.role import router as role_router
from src.api.handlers.role_task import role_tasks_router, task_roles_router
from src.api.handlers.task import router as task_router
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
app.include_router(role_router)
app.include_router(task_router)
app.include_router(task_roles_router)
app.include_router(role_tasks_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
