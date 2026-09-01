import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from scripts import run_backup


class ScheduledBackupTests(unittest.TestCase):
    def test_main_creates_verified_backup_and_reports_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = root / "library.db"
            destination = root / "backups"
            connection = sqlite3.connect(database)
            connection.execute("CREATE TABLE example (value TEXT)")
            connection.commit()
            connection.close()
            output = StringIO()

            with redirect_stdout(output):
                result = run_backup.main(
                    [
                        "--database",
                        str(database),
                        "--backup-dir",
                        str(destination),
                        "--keep-count",
                        "2",
                        "--max-age-days",
                        "120",
                    ]
                )

            report = json.loads(output.getvalue())
            self.assertEqual(result, 0)
            self.assertEqual(report["status"], "ok")
            self.assertEqual(report["pruned"], 0)
            self.assertTrue(Path(report["backup"]).is_file())

    def test_main_hides_database_path_when_backup_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "sensitive-library.db"
            errors = StringIO()

            with redirect_stderr(errors):
                result = run_backup.main(["--database", str(missing)])

            self.assertEqual(result, 1)
            self.assertEqual(
                json.loads(errors.getvalue()),
                {"status": "error", "error": "FileNotFoundError"},
            )
            self.assertNotIn(str(missing), errors.getvalue())


if __name__ == "__main__":
    unittest.main()
