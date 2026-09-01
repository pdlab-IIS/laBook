import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.audit_recovery_sources import audit_recovery_sources


SCHEMA = """
CREATE TABLE Users (user_id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE Books (isbn INTEGER PRIMARY KEY, title TEXT, owner_id INTEGER);
CREATE TABLE Loans (
    loan_id INTEGER PRIMARY KEY,
    isbn TEXT,
    return_date TEXT
);
"""


def make_database(path, users=(), books=(), loans=()):
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    connection.executemany("INSERT INTO Users VALUES (?, ?)", users)
    connection.executemany("INSERT INTO Books VALUES (?, ?, ?)", books)
    connection.executemany("INSERT INTO Loans VALUES (?, ?, ?)", loans)
    connection.commit()
    connection.close()


class RecoverySourceAuditTest(unittest.TestCase):
    def test_reports_recoverability_without_identifiers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            current = root / "library.db"
            make_database(
                current,
                users=[(1, "Current")],
                books=[(100, "Current book", 9)],
                loans=[
                    (1, "200", None),
                    (2, "300", "2026-01-01"),
                ],
            )
            make_database(
                root / "library.db_20260101-000000.db",
                users=[(9, "Historical")],
                books=[(200, "Recovered active book", 9)],
            )
            make_database(
                root / "library.db_20260201-000000.db",
                users=[(1, "Current")],
                books=[(300, "Recovered returned book", 1)],
            )

            report = audit_recovery_sources(current, [root])

            self.assertEqual(report["backup_candidates"], 2)
            self.assertEqual(
                report["targets"],
                {
                    "orphan_isbns": 2,
                    "active_orphan_isbns": 1,
                    "missing_owner_ids": 1,
                },
            )
            self.assertEqual(
                report["recoverable"],
                {
                    "orphan_isbns": 2,
                    "active_orphan_isbns": 1,
                    "missing_owner_ids": 1,
                },
            )
            self.assertIsNone(
                report["newest_complete_source"]["all_orphan_isbns"]
            )
            self.assertNotIn("200", str(report))
            self.assertNotIn("300", str(report))
            self.assertNotIn("Historical", str(report))


if __name__ == "__main__":
    unittest.main()
