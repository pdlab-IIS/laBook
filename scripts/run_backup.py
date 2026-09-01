"""Create one verified database backup and enforce local retention."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from db import DATABASE
from db_backup import create_online_backup, prune_backups


DEFAULT_BACKUP_DIR = Path(DATABASE).parent / "backups" / "daily"


def positive_integer(value):
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def run_backup(
    database_path=DATABASE,
    backup_dir=DEFAULT_BACKUP_DIR,
    *,
    keep_count=90,
    max_age_days=120,
):
    database = Path(database_path).resolve()
    destination = Path(backup_dir).resolve()
    backup_path = create_online_backup(database, destination)
    removed = prune_backups(
        destination,
        database.name,
        keep_count=keep_count,
        max_age_days=max_age_days,
    )
    return backup_path, removed


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=DATABASE)
    parser.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    parser.add_argument("--keep-count", type=positive_integer, default=90)
    parser.add_argument("--max-age-days", type=positive_integer, default=120)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        backup_path, removed = run_backup(
            args.database,
            args.backup_dir,
            keep_count=args.keep_count,
            max_age_days=args.max_age_days,
        )
    except Exception as error:
        print(
            json.dumps(
                {"status": "error", "error": type(error).__name__},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {
                "status": "ok",
                "backup": str(backup_path),
                "pruned": len(removed),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
