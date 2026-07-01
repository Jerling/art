"""Seed a default admin user for local beta testing.

Sprint 4 收尾 — the JWT auth middleware (commit b2e30a1) has been merged
but no login endpoint existed, and no user row existed in the database
either.  This script makes the Web UI actually usable by ensuring there
is always at least one ``admin`` account.

Credentials are read from environment variables (with safe defaults) so
they can be overridden per-environment without touching this script:

    ART_AUTH__DEFAULT_ADMIN_USERNAME    default: admin
    ART_AUTH__DEFAULT_ADMIN_PASSWORD    default: admin

The script is idempotent — running it twice with the same username
will NOT overwrite an existing user's password (deliberate: protects
any hand-crafted password the operator already set).  Re-running with
``--reset`` forces a password rotation.

Usage:
    python -m scripts.seed_admin           # safe / idempotent
    python -m scripts.seed_admin --reset   # rotate password

Exit codes:
    0  user already existed, no change
    1  created new user
    2  error
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Make ``import src.*`` work when running directly (``python scripts/seed_admin.py``)
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


async def _run(reset: bool) -> int:
    # Local imports so os.environ changes from tests don't bleed in
    from sqlalchemy import select

    from src.models import Base, User
    from src.storage.database import async_session_maker, engine
    from src.utils.security import hash_password

    # Ensure tables exist (idempotent)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    username = os.environ.get("ART_AUTH__DEFAULT_ADMIN_USERNAME", "admin")
    password = os.environ.get("ART_AUTH__DEFAULT_ADMIN_PASSWORD", "admin")

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.username == username))
        existing = result.scalar_one_or_none()

        if existing is not None and not reset:
            print(f"[seed_admin] user '{username}' already exists (id={existing.id}); leaving password untouched")
            await engine.dispose()
            return 0

        if existing is None:
            user = User(username=username, password_hash=hash_password(password), is_admin=True)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            print(f"[seed_admin] created admin user '{username}' (id={user.id})")
            await engine.dispose()
            return 1

        # existing + reset → rotate password
        existing.password_hash = hash_password(password)
        await session.commit()
        print(f"[seed_admin] rotated password for existing admin '{username}' (id={existing.id})")
        await engine.dispose()
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed a default admin user.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Rotate the password even if the user already exists.",
    )
    parser.add_argument(
        "--env-file",
        default=str(_ROOT / ".env"),
        help="Path to the .env file to load (default: <repo>/.env). Set to '' to skip.",
    )
    args = parser.parse_args()

    # Load .env so DATABASE_URL, JWT_SECRET_KEY, etc. are available BEFORE
    # src.storage.database creates its engine (the engine reads DATABASE_URL
    # at import time, not at first use).
    if args.env_file:
        env_path = Path(args.env_file)
        if env_path.is_file():
            try:
                from dotenv import load_dotenv

                load_dotenv(env_path, override=False)
            except ImportError:  # pragma: no cover
                print(
                    f"[seed_admin] WARNING: python-dotenv not installed; "
                    f"could not auto-load {env_path}",
                    file=sys.stderr,
                )

    try:
        rc = asyncio.run(_run(reset=args.reset))
    except Exception as exc:  # noqa: BLE001
        print(f"[seed_admin] ERROR: {exc}", file=sys.stderr)
        return 2
    return rc


if __name__ == "__main__":
    sys.exit(main())
