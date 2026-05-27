"""Tests for scripts/backup.py — SQLite online backup."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.backup import (
    BACKUP_FILENAME_RE,
    create_backup,
    prune_old_backups,
    run_backup,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Create a temporary SQLite database with some data."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO users (name) VALUES ('Alice'), ('Bob'), ('Charlie')")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def tmp_backup_dir(tmp_path: Path) -> Path:
    """Create a temporary backup directory."""
    d = tmp_path / "backups"
    d.mkdir()
    return d


# ── Tests: create_backup ─────────────────────────────────────────────────────


class TestCreateBackup:
    def test_backup_file_exists_after_run(self, tmp_db: Path, tmp_backup_dir: Path) -> None:
        """create_backup should produce a .db file in the backup directory."""
        result = create_backup(str(tmp_db), str(tmp_backup_dir))
        assert result.exists()
        assert result.suffix == ".db"
        assert result.parent == tmp_backup_dir

    def test_backup_file_has_timestamp_name(self, tmp_db: Path, tmp_backup_dir: Path) -> None:
        """Backup filename should match the backup_YYYYMMDD_HHMMSS.db pattern."""
        result = create_backup(str(tmp_db), str(tmp_backup_dir))
        assert BACKUP_FILENAME_RE.match(result.name) is not None

    def test_backup_is_valid_sqlite(self, tmp_db: Path, tmp_backup_dir: Path) -> None:
        """The backup should be a valid SQLite database with the same data."""
        backup_path = create_backup(str(tmp_db), str(tmp_backup_dir))
        conn = sqlite3.connect(str(backup_path))
        rows = conn.execute("SELECT name FROM users ORDER BY id").fetchall()
        conn.close()
        assert [r[0] for r in rows] == ["Alice", "Bob", "Charlie"]

    def test_backup_not_empty(self, tmp_db: Path, tmp_backup_dir: Path) -> None:
        """Backup should have non-zero size."""
        result = create_backup(str(tmp_db), str(tmp_backup_dir))
        assert result.stat().st_size > 0

    def test_nonexistent_db_raises(self, tmp_backup_dir: Path) -> None:
        """create_backup should raise FileNotFoundError for a missing database."""
        with pytest.raises(FileNotFoundError):
            create_backup("/nonexistent/art.db", str(tmp_backup_dir))

    def test_creates_backup_dir_if_missing(self, tmp_db: Path, tmp_path: Path) -> None:
        """create_backup should create the backup directory if it doesn't exist."""
        missing_dir = tmp_path / "new_backups"
        assert not missing_dir.exists()
        result = create_backup(str(tmp_db), str(missing_dir))
        assert missing_dir.exists()
        assert result.exists()


# ── Tests: prune_old_backups ─────────────────────────────────────────────────


class TestPruneOldBackups:
    def _make_backup(self, backup_dir: Path, name: str) -> Path:
        """Create a fake backup file and return its path."""
        p = backup_dir / name
        p.write_bytes(b"fake backup data")
        return p

    def test_prunes_oldest_first(self, tmp_backup_dir: Path) -> None:
        """When there are more backups than `keep`, the oldest should be removed."""
        self._make_backup(tmp_backup_dir, "backup_20260101_000000.db")
        self._make_backup(tmp_backup_dir, "backup_20260102_000000.db")
        self._make_backup(tmp_backup_dir, "backup_20260103_000000.db")
        self._make_backup(tmp_backup_dir, "backup_20260104_000000.db")

        removed = prune_old_backups(str(tmp_backup_dir), keep=2)
        assert len(removed) == 2
        remaining = list(tmp_backup_dir.iterdir())
        assert len(remaining) == 2
        remaining_names = {p.name for p in remaining}
        assert remaining_names == {"backup_20260104_000000.db", "backup_20260103_000000.db"}

    def test_no_prune_when_within_limit(self, tmp_backup_dir: Path) -> None:
        """When backup count <= keep, nothing should be removed."""
        self._make_backup(tmp_backup_dir, "backup_20260101_000000.db")
        self._make_backup(tmp_backup_dir, "backup_20260102_000000.db")

        removed = prune_old_backups(str(tmp_backup_dir), keep=7)
        assert len(removed) == 0
        assert len(list(tmp_backup_dir.iterdir())) == 2

    def test_empty_dir_returns_empty(self, tmp_backup_dir: Path) -> None:
        """Pruning an empty directory should return an empty list."""
        removed = prune_old_backups(str(tmp_backup_dir), keep=7)
        assert removed == []

    def test_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        """Pruning a non-existent directory should return an empty list."""
        removed = prune_old_backups(str(tmp_path / "no_such_dir"), keep=7)
        assert removed == []

    def test_ignores_non_backup_files(self, tmp_backup_dir: Path) -> None:
        """Files that don't match the backup pattern should be ignored."""
        (tmp_backup_dir / "README.md").write_text("hello")
        (tmp_backup_dir / "art.db").write_bytes(b"not a backup")
        self._make_backup(tmp_backup_dir, "backup_20260101_000000.db")

        prune_old_backups(str(tmp_backup_dir), keep=1)
        remaining = list(tmp_backup_dir.iterdir())
        # Should still have README.md, art.db, and the one backup
        remaining_names = {p.name for p in remaining}
        assert "README.md" in remaining_names
        assert "art.db" in remaining_names
        assert "backup_20260101_000000.db" in remaining_names


# ── Tests: run_backup (full cycle) ────────────────────────────────────────────


class TestRunBackup:
    def test_returns_dict_with_expected_keys(self, tmp_db: Path, tmp_backup_dir: Path) -> None:
        """run_backup should return a dict with backup_file, backup_size_mb, pruned_count."""
        result = run_backup(str(tmp_db), str(tmp_backup_dir), keep=7)
        assert "backup_file" in result
        assert "backup_size_mb" in result
        assert "pruned_count" in result
        assert "pruned_files" in result
        assert isinstance(result["backup_file"], str)
        assert isinstance(result["backup_size_mb"], float)
        assert isinstance(result["pruned_count"], int)

    def test_backup_file_on_disk_matches_result(self, tmp_db: Path, tmp_backup_dir: Path) -> None:
        """The file path in the result should exist on disk."""
        result = run_backup(str(tmp_db), str(tmp_backup_dir), keep=7)
        assert Path(result["backup_file"]).exists()

    def test_prunes_excess_backups(self, tmp_db: Path, tmp_backup_dir: Path) -> None:
        """run_backup should prune backups exceeding the keep count."""
        # Pre-populate with 5 fake backups
        for i in range(5):
            ts = f"2025010{i+1}_000000"
            p = tmp_backup_dir / f"backup_{ts}.db"
            p.write_bytes(b"fake")

        result = run_backup(str(tmp_db), str(tmp_backup_dir), keep=3)
        # 5 old + 1 new = 6, keep=3, so 3 should be pruned
        assert result["pruned_count"] == 3
        # The new backup (current timestamp) sorts as newest, plus 2 oldest retained = 3 total
        backup_files = list(tmp_backup_dir.glob("backup_*.db"))
        assert len(backup_files) == 3
