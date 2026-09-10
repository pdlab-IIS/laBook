"""Find aggregate recovery candidates in historical laBook backups."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def _connect_read_only(path):
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def _target_sets(current_database):
    connection = _connect_read_only(current_database)
    try:
        orphan_isbns = {
            str(row[0])
            for row in connection.execute(
                """SELECT DISTINCT loan.isbn
                   FROM Loans AS loan
                   WHERE loan.isbn IS NOT NULL
                     AND NOT EXISTS (
                         SELECT 1 FROM Books AS book WHERE book.isbn = loan.isbn
                     )"""
            )
        }
        active_orphan_isbns = {
            str(row[0])
            for row in connection.execute(
                """SELECT DISTINCT loan.isbn
                   FROM Loans AS loan
                   WHERE loan.isbn IS NOT NULL
                     AND loan.return_date IS NULL
                     AND NOT EXISTS (
                         SELECT 1 FROM Books AS book WHERE book.isbn = loan.isbn
                     )"""
            )
        }
        missing_owner_ids = {
            str(row[0])
            for row in connection.execute(
                """SELECT DISTINCT book.owner_id
                   FROM Books AS book
                   WHERE book.owner_id IS NOT NULL
                     AND book.owner_id <> 0
                     AND TRIM(CAST(book.owner_id AS TEXT)) <> ''
                     AND NOT EXISTS (
                         SELECT 1 FROM Users AS user
                         WHERE user.user_id = book.owner_id
                     )"""
            )
        }
    finally:
        connection.close()
    return orphan_isbns, active_orphan_isbns, missing_owner_ids


def _newest_path(candidates):
    if not candidates:
        return None
    return str(max(candidates, key=lambda path: path.stat().st_mtime))


def audit_recovery_sources(current_database, backup_roots):
    """Scan backups and report recoverability without printing identifiers."""
    current_path = Path(current_database).resolve()
    orphan_isbns, active_orphan_isbns, missing_owner_ids = _target_sets(current_path)

    candidates = set()
    for backup_root in backup_roots:
        root = Path(backup_root).resolve()
        candidates.update(root.rglob("library.db_*.db"))
    candidates.discard(current_path)

    recovered_orphan_isbns = set()
    recovered_active_orphan_isbns = set()
    recovered_missing_owner_ids = set()
    all_orphan_sources = []
    all_active_orphan_sources = []
    all_missing_owner_sources = []
    readable_backups = 0
    unreadable_backups = 0

    for backup_path in sorted(candidates):
        if not backup_path.is_file():
            continue
        try:
            connection = _connect_read_only(backup_path)
            try:
                book_isbns = {
                    str(row[0])
                    for row in connection.execute("SELECT isbn FROM Books")
                }
                user_ids = {
                    str(row[0])
                    for row in connection.execute("SELECT user_id FROM Users")
                }
            finally:
                connection.close()
        except (OSError, sqlite3.DatabaseError, TypeError, ValueError):
            unreadable_backups += 1
            continue

        readable_backups += 1
        recovered_orphan_isbns.update(orphan_isbns & book_isbns)
        recovered_active_orphan_isbns.update(active_orphan_isbns & book_isbns)
        recovered_missing_owner_ids.update(missing_owner_ids & user_ids)

        if orphan_isbns and orphan_isbns <= book_isbns:
            all_orphan_sources.append(backup_path)
        if active_orphan_isbns and active_orphan_isbns <= book_isbns:
            all_active_orphan_sources.append(backup_path)
        if missing_owner_ids and missing_owner_ids <= user_ids:
            all_missing_owner_sources.append(backup_path)

    return {
        "backup_candidates": len(candidates),
        "readable_backups": readable_backups,
        "unreadable_backups": unreadable_backups,
        "targets": {
            "orphan_isbns": len(orphan_isbns),
            "active_orphan_isbns": len(active_orphan_isbns),
            "missing_owner_ids": len(missing_owner_ids),
        },
        "recoverable": {
            "orphan_isbns": len(recovered_orphan_isbns),
            "active_orphan_isbns": len(recovered_active_orphan_isbns),
            "missing_owner_ids": len(recovered_missing_owner_ids),
        },
        "newest_complete_source": {
            "all_orphan_isbns": _newest_path(all_orphan_sources),
            "all_active_orphan_isbns": _newest_path(all_active_orphan_sources),
            "all_missing_owner_ids": _newest_path(all_missing_owner_sources),
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Find aggregate recovery candidates in laBook backups."
    )
    parser.add_argument("current_database")
    parser.add_argument(
        "backup_roots",
        nargs="+",
        help="Directories recursively searched for library.db_*.db",
    )
    args = parser.parse_args(argv)
    report = audit_recovery_sources(args.current_database, args.backup_roots)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
