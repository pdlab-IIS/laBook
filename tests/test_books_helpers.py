import sqlite3
import unittest

from routes.books import get_or_create_shelf_id, normalize_owner_id


class ShelfHelperTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute(
            """CREATE TABLE Shelves (
                shelf_id INTEGER PRIMARY KEY AUTOINCREMENT,
                shelf_code TEXT NOT NULL UNIQUE,
                location_description TEXT
            )"""
        )

    def tearDown(self):
        self.db.close()

    def test_creates_then_reuses_shelf_in_same_database_transaction(self):
        first_id = get_or_create_shelf_id(self.db, " A1 ", "First floor")
        second_id = get_or_create_shelf_id(self.db, "A1", "Ignored update")

        self.assertEqual(first_id, second_id)
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM Shelves").fetchone()[0],
            1,
        )
        self.assertEqual(
            self.db.execute(
                "SELECT location_description FROM Shelves WHERE shelf_id = ?",
                (first_id,),
            ).fetchone()[0],
            "First floor",
        )

    def test_blank_shelf_code_does_not_create_shelf(self):
        self.assertIsNone(get_or_create_shelf_id(self.db, "   "))
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM Shelves").fetchone()[0],
            0,
        )


class OwnerIdTests(unittest.TestCase):
    def test_historical_zero_sentinel_becomes_null(self):
        for value in (None, "", 0, "0"):
            with self.subTest(value=value):
                self.assertIsNone(normalize_owner_id(value))

    def test_nonzero_owner_id_is_preserved_for_later_migration(self):
        self.assertEqual(normalize_owner_id("42"), "42")


if __name__ == "__main__":
    unittest.main()
