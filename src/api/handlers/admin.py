"""Admin database backup handler.

POST /api/v1/admin/backup  — trigger an immediate SQLite backup
GET  /api/v1/admin/backup  — list available backups
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# Default paths — derive DB location from DATABASE_URL, fall back to Docker-compatible default
# Docker volume maps ./data → /app/data, so the real DB is at /app/data/art.db
_default_db_path = str(Path(__file__).parent.parent.parent.parent / "data" / "art.db")
_db_url = os.environ.get("DATABASE_URL", "")
if _db_url:
    _m = re.match(r"sqlite(?:\+aiosqlite)?:///(.+)", _db_url)
    if _m:
        # Resolve relative paths (e.g. "./data/art.db") to absolute
        _default_db_path = str(Path(_m.group(1)).resolve())
DEFAULT_DB_PATH = _default_db_path
DEFAULT_BACKUP_DIR = str(Path(__file__).parent.parent.parent.parent / "data" / "backups")
DEFAULT_KEEP = 7


@router.post(
    "/backup",
    summary="Trigger database backup",
    description="Creates an online SQLite backup using VACUUM INTO. Retains the most recent N backups.",
)
async def trigger_backup(
    db_path: str = Query(DEFAULT_DB_PATH, description="Source database path"),
    backup_dir: str = Query(DEFAULT_BACKUP_DIR, description="Backup output directory"),
    keep: int = Query(DEFAULT_KEEP, ge=1, le=365, description="Number of backups to retain"),
) -> dict:
    """Trigger an immediate SQLite backup.

    Uses VACUUM INTO for zero-downtime online backup.
    Old backups beyond the retention count are pruned automatically.
    """
    from scripts.backup import run_backup

    try:
        result = await asyncio.to_thread(run_backup, db_path, backup_dir, keep)
    except FileNotFoundError as exc:
        logger.error("Backup failed: %s", exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Backup failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Backup failed: {exc}") from exc

    return {
        "status": "ok",
        "backup_file": result["backup_file"],
        "backup_size_mb": result["backup_size_mb"],
        "pruned_count": result["pruned_count"],
    }


@router.get(
    "/backup",
    summary="List available backups",
    description="Returns a list of available backup files with their sizes and timestamps.",
)
async def list_backups(
    backup_dir: str = Query(DEFAULT_BACKUP_DIR, description="Backup directory to scan"),
) -> dict:
    """List available backup files."""
    import re
    from datetime import datetime

    BACKUP_RE = re.compile(r"^backup_(\d{8}_\d{6})\.db$")
    out_dir = Path(backup_dir)

    if not out_dir.exists():
        return {"backups": [], "count": 0}

    backups = []
    for entry in sorted(out_dir.iterdir(), reverse=True):
        if entry.is_file():
            m = BACKUP_RE.match(entry.name)
            if m:
                ts_str = m.group(1)
                try:
                    dt = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
                except ValueError:
                    dt = None
                backups.append(
                    {
                        "filename": entry.name,
                        "size_mb": round(entry.stat().st_size / (1024 * 1024), 2),
                        "created": dt.isoformat() if dt else ts_str,
                    }
                )

    return {"backups": backups, "count": len(backups)}
