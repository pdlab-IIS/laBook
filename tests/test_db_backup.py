import sqlite3
import tempfile
import unittest
from pathlib import Path

from db_backup import create_online_backup


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


if __name__ == "__main__":
    unittest.main()
