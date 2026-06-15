"""Root conftest: set required env vars and ensure DB schema for tests.

Two responsibilities:

1. **Env vars** — the JWT_SECRET_KEY validator in src/utils/config.py raises
   if the env var is unset, so we set a deterministic test value here.

2. **DB schema** — the base main test suite historically relied on a side
   effect from tests/pre_beta_self_test.py (its top-level
   `asyncio.run(init_db())`) to create the SQLite tables. Now that
   pre_beta_self_test is excluded from pytest collection, that side
   effect no longer runs, so we recreate the schema here in a session-
   scoped autouse fixture.

   We use the default DATABASE_URL (`sqlite+aiosqlite:///./art.db`) so
   the in-process engine that src/storage/database.py builds sees the
   same schema. Tests that need a different storage backend should
   override DATABASE_URL via local env / fixture.
"""
from __future__ import annotations

import asyncio
import os

# Stable test value; intentionally non-secret — only used by unit tests.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only-do-not-use-in-prod")


import pytest


@pytest.fixture(scope="session", autouse=True)
def _ensure_db_schema() -> None:
    """Create all SQLAlchemy tables once per test session.

    Replaces the implicit schema-creation side effect that used to live
    in tests/pre_beta_self_test.py. Without this, HTTP-level tests
    fail with "no such table: tasks/roles".
    """
    # Import inside the fixture so os.environ above takes effect first
    # (src/utils/config.py reads JWT_SECRET_KEY at import time).
    from src.models import Base  # noqa: WPS433 (intentional local import)
    from src.storage.database import engine

    async def _create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())
    try:
        yield
    finally:
        async def _drop() -> None:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)

        try:
            asyncio.run(_drop())
        except Exception:
            # Don't mask test failures with cleanup errors.
            pass



def resolve_intent_date_markers(obj):
    """Recursively replace {"_days_from_today": N} markers with ISO dates.

    Used by intent golden-dataset loaders: the fixture file stores dates
    as semantic offsets (so it does not rot as the calendar advances),
    and this function expands them to concrete ISO strings at test load
    time. Day 0 (today) is preserved; negative offsets are allowed and
    will fail downstream past-date guards (intentional).
    """
    from datetime import date, timedelta

    if isinstance(obj, dict):
        if set(obj.keys()) == {"_days_from_today"} and isinstance(obj["_days_from_today"], int):
            return (date.today() + timedelta(days=obj["_days_from_today"])).isoformat()
        return {k: resolve_intent_date_markers(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_intent_date_markers(v) for v in obj]
    return obj
