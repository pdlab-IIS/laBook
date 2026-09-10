"""Consistent SQLite backups for the web app and scheduled subapp."""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from pathlib import Path


class BackupError(RuntimeError):
    """Raised when a generated backup fails its integrity check."""


BACKUP_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S-%f"


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

    timestamp = datetime.datetime.now().strftime(BACKUP_TIMESTAMP_FORMAT)
    destination_path = destination_dir / f"{source_path.name}_{timestamp}.db"
    source_uri = f"{source_path.as_uri()}?mode=ro"

    descriptor = os.open(
        destination_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    os.close(descriptor)

    source = None
    try:
        source = sqlite3.connect(source_uri, uri=True)
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
        if source is not None:
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


def prune_backups(
    backup_dir,
    source_filename,
    *,
    keep_count=90,
    max_age_days=120,
    reference_time=None,
):
    """Remove expired backups while always preserving the newest one.

    Only regular, non-symlink files produced by ``create_online_backup`` for
    the requested source filename are eligible. Call this only after a new
    backup has passed its integrity check.
    """
    if keep_count < 1:
        raise ValueError("keep_count must be at least 1")
    if max_age_days < 1:
        raise ValueError("max_age_days must be at least 1")

    directory = Path(backup_dir).resolve()
    if not directory.is_dir():
        return []

    pattern = re.compile(
        rf"^{re.escape(source_filename)}_"
        rf"(?P<timestamp>\d{{8}}-\d{{6}}-\d{{6}})\.db$"
    )
    candidates = []
    for path in directory.iterdir():
        match = pattern.fullmatch(path.name)
        if not match or path.is_symlink() or not path.is_file():
            continue
        try:
            created_at = datetime.datetime.strptime(
                match.group("timestamp"),
                BACKUP_TIMESTAMP_FORMAT,
            )
        except ValueError:
            continue
        candidates.append((created_at, path))

    candidates.sort(key=lambda item: (item[0], item[1].name), reverse=True)
    if not candidates:
        return []

    now = reference_time or datetime.datetime.now()
    cutoff = now - datetime.timedelta(days=max_age_days)
    removed = []
    for index, (created_at, path) in enumerate(candidates):
        if index == 0:
            continue
        if index >= keep_count or created_at < cutoff:
            path.unlink()
            removed.append(path)

    return removed
