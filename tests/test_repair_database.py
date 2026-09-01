import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.repair_database import (
    LOAN_ARCHIVE_DELETE,
    OWNER_ARCHIVE_NULL,
    RepairPolicyError,
    RepairValidationError,
    audit_database,
    repair_database,
)


SCHEMA = """
CREATE TABLE Users (
    user_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE Shelves (
    shelf_id INTEGER PRIMARY KEY,
    shelf_code TEXT NOT NULL UNIQUE
);
CREATE TABLE Books (
    isbn INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    owner_id INTEGER,
    shelf_id INTEGER,
    FOREIGN KEY(owner_id) REFERENCES Users(user_id),
    FOREIGN KEY(shelf_id) REFERENCES Shelves(shelf_id)
);
CREATE TABLE Loans (
    loan_id INTEGER PRIMARY KEY,
    isbn TEXT,
    borrower_id INTEGER,
    returner_id INTEGER,
    loan_date TEXT NOT NULL,
    due_date TEXT,
    return_date TEXT,
    FOREIGN KEY(isbn) REFERENCES Books(isbn),
    FOREIGN KEY(borrower_id) REFERENCES Users(user_id),
    FOREIGN KEY(returner_id) REFERENCES Users(user_id)
);
"""


class RepairDatabaseTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.database = self.root / "library.db"
        connection = sqlite3.connect(self.database)
        connection.executescript(SCHEMA)
        connection.execute("INSERT INTO Users VALUES (1, 'Valid user')")
        connection.execute("INSERT INTO Shelves VALUES (1, 'A1')")
        connection.executemany(
            "INSERT INTO Books VALUES (?, ?, ?, ?)",
            [
                (100, "Valid owner", 1, 1),
                (101, "Zero owner", 0, 1),
                (102, "Missing owner", 99, 1),
            ],
        )
        connection.executemany(
            "INSERT INTO Loans VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (1, "100", 1, None, "2026-01-01", None, "2026-01-02"),
                (2, "999", 1, None, "2026-02-01", None, None),
            ],
        )
        connection.commit()
        connection.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_dry_run_uses_memory_copy_and_leaves_source_unchanged(self):
        original = self.database.read_bytes()

        report = repair_database(
            self.database,
            owner_policy=OWNER_ARCHIVE_NULL,
            orphan_loan_policy=LOAN_ARCHIVE_DELETE,
        )

        self.assertEqual(report["mode"], "dry-run")
        self.assertEqual(report["before"]["foreign_key_violations"], 3)
        self.assertEqual(report["projected"]["foreign_key_violations"], 0)
        self.assertEqual(
            report["changes"],
            {
                "book_owners_archived_and_nullified": 2,
                "orphan_loans_archived_and_deleted": 1,
            },
        )
        self.assertEqual(self.database.read_bytes(), original)
        connection = sqlite3.connect(self.database)
        self.assertFalse(
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name = 'LoansOrphanArchive'"
            ).fetchone()
        )
        connection.close()

    def test_apply_archives_data_creates_backup_and_clears_violations(self):
        backup_dir = self.root / "backup"
        report = repair_database(
            self.database,
            apply=True,
            owner_policy=OWNER_ARCHIVE_NULL,
            orphan_loan_policy=LOAN_ARCHIVE_DELETE,
            backup_dir=backup_dir,
        )

        self.assertEqual(report["mode"], "apply")
        self.assertEqual(report["after"]["foreign_key_violations"], 0)
        self.assertEqual(report["after"]["archived_book_owners"], 2)
        self.assertEqual(report["after"]["archived_orphan_loans"], 1)

        backup = Path(report["backup"])
        self.assertTrue(backup.is_file())
        backup_connection = sqlite3.connect(backup)
        self.assertEqual(
            audit_database(backup_connection).foreign_key_violations,
            3,
        )
        backup_connection.close()

        connection = sqlite3.connect(self.database)
        owners = connection.execute(
            "SELECT isbn, owner_id FROM Books ORDER BY isbn"
        ).fetchall()
        self.assertEqual(owners, [(100, 1), (101, None), (102, None)])
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM Loans").fetchone()[0], 1)
        connection.close()

    def test_apply_requires_explicit_policies(self):
        with self.assertRaises(RepairPolicyError):
            repair_database(self.database, apply=True)
        self.assertFalse((self.root / "backups").exists())

    def test_unhandled_violation_rolls_back_all_changes(self):
        connection = sqlite3.connect(self.database)
        connection.execute("UPDATE Books SET shelf_id = 404 WHERE isbn = 100")
        connection.commit()
        connection.close()

        with self.assertRaises(RepairValidationError) as caught:
            repair_database(
                self.database,
                apply=True,
                owner_policy=OWNER_ARCHIVE_NULL,
                orphan_loan_policy=LOAN_ARCHIVE_DELETE,
                backup_dir=self.root / "rollback-backup",
            )
        self.assertIn("pre-migration backup", str(caught.exception))

        connection = sqlite3.connect(self.database)
        self.assertEqual(
            connection.execute(
                "SELECT owner_id FROM Books WHERE isbn = 101"
            ).fetchone()[0],
            0,
        )
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM Loans").fetchone()[0], 2)
        self.assertFalse(
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name = 'BookOwnerRepairArchive'"
            ).fetchone()
        )
        connection.close()


if __name__ == "__main__":
    unittest.main()
