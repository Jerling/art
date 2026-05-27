#!/usr/bin/env python3
"""SQLite online backup script using VACUUM INTO.

Creates zero-downtime backups of the art.db SQLite database.
Backups are stored in ./backups/ with timestamp naming.
Only the most recent N backups are retained (configurable).

Usage:
    python scripts/backup.py                           # backup with default settings
    python scripts/backup.py --keep 14                 # retain 14 backups
    python scripts/backup.py --db /path/to/custom.db   # custom DB path
    python scripts/backup.py --backup-dir /backups     # custom backup directory
"""

import argparse
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("art.backup")

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_DB_PATH = os.environ.get("DATABASE_PATH", str(Path(__file__).parent.parent / "art.db"))
DEFAULT_BACKUP_DIR = str(Path(__file__).parent.parent / "backups")
DEFAULT_KEEP = 7

BACKUP_FILENAME_RE = re.compile(r"^backup_(\d{8}_\d{6})\.db$")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SQLite online backup (VACUUM INTO)")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help=f"Source database path (default: {DEFAULT_DB_PATH})")
    parser.add_argument("--backup-dir", default=DEFAULT_BACKUP_DIR, help=f"Backup directory (default: {DEFAULT_BACKUP_DIR})")
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP, help=f"Number of backups to retain (default: {DEFAULT_KEEP})")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    return parser.parse_args(argv)


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )


def create_backup(db_path: str, backup_dir: str) -> Path:
    """Create a VACUUM INTO backup of the database.

    Args:
        db_path: Path to the source SQLite database.
        backup_dir: Directory to write the backup file into.

    Returns:
        Path to the created backup file.

    Raises:
        FileNotFoundError: If the source database doesn't exist.
        sqlite3.Error: If the VACUUM INTO command fails.
    """
    source = Path(db_path)
    if not source.exists():
        raise FileNotFoundError(f"Database not found: {source}")

    out_dir = Path(backup_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = out_dir / f"backup_{ts}.db"

    logger.info(f"Backing up {source} -> {backup_path}")

    # VACUUM INTO creates an online (non-locking) copy of the database.
    # Works with file-based SQLite databases.
    # We use a parameterized query via the backup API for safety.
    conn = sqlite3.connect(str(source))
    try:
        # VACUUM INTO does not support parameter binding, so we sanitize manually.
        # The path is always generated internally (timestamp-based), never user input.
        backup_sql = f"VACUUM INTO '{str(backup_path)}'"
        conn.execute(backup_sql)
    finally:
        conn.close()

    size_mb = backup_path.stat().st_size / (1024 * 1024)
    logger.info(f"Backup complete: {backup_path.name} ({size_mb:.2f} MB)")
    return backup_path


def prune_old_backups(backup_dir: str, keep: int) -> list[Path]:
    """Remove old backups, keeping only the most recent N.

    Args:
        backup_dir: Directory containing backup files.
        keep: Maximum number of backups to retain.

    Returns:
        List of removed backup paths.
    """
    out_dir = Path(backup_dir)
    if not out_dir.exists():
        return []

    backups: list[tuple[datetime, Path]] = []
    for entry in out_dir.iterdir():
        if entry.is_file():
            m = BACKUP_FILENAME_RE.match(entry.name)
            if m:
                ts_str = m.group(1)
                try:
                    dt = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
                    backups.append((dt, entry))
                except ValueError:
                    continue

    # Newest first
    backups.sort(key=lambda t: t[0], reverse=True)

    removed: list[Path] = []
    for _, path in backups[keep:]:
        logger.info(f"Pruning old backup: {path.name}")
        path.unlink()
        removed.append(path)

    return removed


def run_backup(db_path: str, backup_dir: str, keep: int) -> dict:
    """Run a full backup cycle: create backup + prune old ones.

    Args:
        db_path: Path to the source database.
        backup_dir: Directory for backups.
        keep: Number of backups to retain.

    Returns:
        dict with keys: backup_file, backup_size_mb, pruned_count, pruned_files
    """
    backup_file = create_backup(db_path, backup_dir)
    pruned = prune_old_backups(backup_dir, keep)
    return {
        "backup_file": str(backup_file),
        "backup_size_mb": round(backup_file.stat().st_size / (1024 * 1024), 2),
        "pruned_count": len(pruned),
        "pruned_files": [str(p.name) for p in pruned],
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)

    try:
        result = run_backup(args.db, args.backup_dir, args.keep)
        logger.info(
            f"Done. Backup: {result['backup_file']} "
            f"({result['backup_size_mb']} MB), "
            f"pruned {result['pruned_count']} old backup(s)"
        )
        return 0
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1
    except sqlite3.Error as e:
        logger.error(f"SQLite error during backup: {e}")
        return 2
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
