"""Consistent SQLite backups for the web app and scheduled subapp."""

from __future__ import annotations

import datetime
import os
import sqlite3
from pathlib import Path


class BackupError(RuntimeError):
    """Raised when a generated backup fails its integrity check."""


def create_online_backup(database_path, backup_dir=None):
    """Create and verify a transactionally consistent SQLite backup.

    The source is opened read-only. The returned file is mode 0600 on platforms
    that support POSIX-style permission bits.
    """
    source_path = Path(database_path).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    destination_dir = (
        Path(backup_dir).resolve() if backup_dir else source_path.parent
    )
    destination_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination_path = destination_dir / f"{source_path.name}_{timestamp}.db"
    source_uri = f"{source_path.as_uri()}?mode=ro"

    source = sqlite3.connect(source_uri, uri=True)
    try:
        destination = sqlite3.connect(destination_path)
        try:
            source.backup(destination)
            destination.commit()
        finally:
            destination.close()
    except Exception:
        destination_path.unlink(missing_ok=True)
        raise
    finally:
        source.close()

    check = sqlite3.connect(f"{destination_path.as_uri()}?mode=ro", uri=True)
    try:
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        check.close()

    if integrity != "ok":
        destination_path.unlink(missing_ok=True)
        raise BackupError(f"Backup integrity check failed: {integrity}")

    try:
        os.chmod(destination_path, 0o600)
    except OSError:
        # Permission semantics vary on Windows; deployment runs on Linux.
        pass

    return destination_path
