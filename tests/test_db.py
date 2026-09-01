import sqlite3
import tempfile
import unittest
from pathlib import Path

from db import BUSY_TIMEOUT_MS, connect_database


class DatabaseConnectionTest(unittest.TestCase):
    def test_enables_foreign_keys_and_busy_timeout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "library.db"
            connection = connect_database(database)
            try:
                self.assertEqual(
                    connection.execute("PRAGMA foreign_keys").fetchone()[0],
                    1,
                )
                self.assertEqual(
                    connection.execute("PRAGMA busy_timeout").fetchone()[0],
                    BUSY_TIMEOUT_MS,
                )
                connection.executescript(
                    """
                    CREATE TABLE parent (id INTEGER PRIMARY KEY);
                    CREATE TABLE child (
                        id INTEGER PRIMARY KEY,
                        parent_id INTEGER,
                        FOREIGN KEY(parent_id) REFERENCES parent(id)
                    );
                    """
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "INSERT INTO child (id, parent_id) VALUES (1, 404)"
                    )
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
