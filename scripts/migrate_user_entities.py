"""Back up and explicitly migrate an existing laBook database."""

import argparse
import json
import sqlite3
from pathlib import Path

from db_backup import create_online_backup
from user_entities import migrate_user_entities


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args()
    path = args.database.resolve(strict=True)
    backup = None
    if args.apply:
        backup = create_online_backup(path, args.backup_dir or path.parent / "backups" / "user-entities")
    with sqlite3.connect(path.as_uri() + ("?mode=rw" if args.apply else "?mode=ro"), uri=True) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        if args.apply:
            migrate_user_entities(connection)
        print(json.dumps({"applied": args.apply, "backup": str(backup) if backup else None,
                          "columns": [row[1] for row in connection.execute("PRAGMA table_info(Users)")],
                          "integrity": connection.execute("PRAGMA integrity_check").fetchone()[0]}))


if __name__ == "__main__":
    main()
