"""Database configuration and session factory."""
import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./art.db")

engine = create_async_engine(DATABASE_URL, echo=False, future=True)

async_session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency: yield an async session."""
    async with async_session_maker() as session:
        yield session
