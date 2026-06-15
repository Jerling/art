"""Root conftest: ensure required env vars exist before any test imports the app.

The JWT_SECRET_KEY validator in src/utils/config.py raises if the env var
is unset, so we set a deterministic test value here. The database URL is
left at its default (file-backed SQLite under ./art.db) so connections
in a single process share the same schema. Tests that need a fresh
schema or a different storage backend should override locally.
"""
from __future__ import annotations

import os

# Stable test value; intentionally non-secret — only used by unit tests.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only-do-not-use-in-prod")
