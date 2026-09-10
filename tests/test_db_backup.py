import datetime
import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path

from db_backup import create_online_backup, prune_backups


class OnlineBackupTests(unittest.TestCase):
    def test_creates_integrity_checked_copy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.db"
            backup_dir = temp_path / "backups"

            source = sqlite3.connect(source_path)
            source.execute("CREATE TABLE example (id INTEGER PRIMARY KEY, value TEXT)")
            source.execute("INSERT INTO example (value) VALUES (?)", ("saved",))
            source.commit()
            source.close()

            backup_path = create_online_backup(source_path, backup_dir)

            self.assertTrue(backup_path.is_file())
            self.assertEqual(backup_path.parent, backup_dir)
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(backup_path.stat().st_mode), 0o600)
            backup = sqlite3.connect(
                f"{backup_path.resolve().as_uri()}?mode=ro",
                uri=True,
            )
            try:
                self.assertEqual(
                    backup.execute("PRAGMA integrity_check").fetchone()[0],
                    "ok",
                )
                self.assertEqual(
                    backup.execute("SELECT value FROM example").fetchone()[0],
                    "saved",
                )
            finally:
                backup.close()

    def test_missing_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "missing.db"
            with self.assertRaises(FileNotFoundError):
                create_online_backup(missing_path)

    def test_prune_enforces_count_without_touching_unrelated_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_dir = Path(temp_dir)
            names = [
                "library.db_20260901-030000-000000.db",
                "library.db_20260831-030000-000000.db",
                "library.db_20260830-030000-000000.db",
                "library.db_20260829-030000-000000.db",
            ]
            for name in names:
                (backup_dir / name).touch()
            unrelated = backup_dir / "other.db_20200101-000000-000000.db"
            unrelated.touch()

            removed = prune_backups(
                backup_dir,
                "library.db",
                keep_count=2,
                max_age_days=120,
                reference_time=datetime.datetime(2026, 9, 1, 12, 0),
            )

            self.assertEqual(
                {path.name for path in removed},
                set(names[2:]),
            )
            self.assertTrue((backup_dir / names[0]).exists())
            self.assertTrue((backup_dir / names[1]).exists())
            self.assertTrue(unrelated.exists())

    def test_prune_enforces_age_but_preserves_newest_backup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_dir = Path(temp_dir)
            newest = backup_dir / "library.db_20260101-030000-000000.db"
            older = backup_dir / "library.db_20251231-030000-000000.db"
            newest.touch()
            older.touch()

            removed = prune_backups(
                backup_dir,
                "library.db",
                keep_count=90,
                max_age_days=120,
                reference_time=datetime.datetime(2026, 9, 1, 12, 0),
            )

            self.assertEqual(removed, [older.resolve()])
            self.assertTrue(newest.exists())
            self.assertFalse(older.exists())

    def test_prune_rejects_a_policy_that_could_remove_every_backup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                prune_backups(temp_dir, "library.db", keep_count=0)
            with self.assertRaises(ValueError):
                prune_backups(temp_dir, "library.db", max_age_days=0)


if __name__ == "__main__":
    unittest.main()
