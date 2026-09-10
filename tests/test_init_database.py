import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from scripts import init_database


class InitializeDatabaseTests(unittest.TestCase):
    def test_creates_new_database_with_expected_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "library.db"
            output = StringIO()

            with redirect_stdout(output):
                result = init_database.main(["--database", str(database)])

            self.assertEqual(result, 0)
            self.assertEqual(json.loads(output.getvalue()), {"status": "ok"})
            connection = sqlite3.connect(database)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            finally:
                connection.close()
            self.assertTrue({"Users", "Shelves", "Books", "Loans"} <= tables)

    def test_refuses_to_modify_existing_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "library.db"
            database.write_bytes(b"do-not-overwrite")
            errors = StringIO()

            with redirect_stderr(errors):
                result = init_database.main(["--database", str(database)])

            self.assertEqual(result, 1)
            self.assertEqual(database.read_bytes(), b"do-not-overwrite")
            self.assertEqual(
                json.loads(errors.getvalue()),
                {"status": "error", "error": "FileExistsError"},
            )
            self.assertNotIn(str(database), errors.getvalue())


if __name__ == "__main__":
    unittest.main()
