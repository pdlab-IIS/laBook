import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import app
from db import connect_database
from user_entities import migrate_user_entities


SCHEMA = """
CREATE TABLE Users (
    user_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE Shelves (
    shelf_id INTEGER PRIMARY KEY,
    shelf_code TEXT NOT NULL UNIQUE,
    location_description TEXT
);
CREATE TABLE Books (
    isbn INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT,
    publisher TEXT,
    publication_date TEXT,
    cover_image_path TEXT,
    owner_id INTEGER,
    comment TEXT,
    shelf_id INTEGER,
    updatedtime TEXT,
    FOREIGN KEY(owner_id) REFERENCES Users(user_id) ON DELETE RESTRICT,
    FOREIGN KEY(shelf_id) REFERENCES Shelves(shelf_id) ON DELETE RESTRICT
);
CREATE TABLE Loans (
    loan_id INTEGER PRIMARY KEY,
    isbn TEXT NOT NULL,
    borrower_id INTEGER NOT NULL,
    returner_id INTEGER,
    loan_date TEXT NOT NULL,
    due_date TEXT,
    return_date TEXT,
    FOREIGN KEY(isbn) REFERENCES Books(isbn) ON DELETE RESTRICT,
    FOREIGN KEY(borrower_id) REFERENCES Users(user_id) ON DELETE RESTRICT,
    FOREIGN KEY(returner_id) REFERENCES Users(user_id) ON DELETE RESTRICT
);
"""


class IntegrityErrorRouteTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "library.db"
        connection = connect_database(self.database)
        connection.executescript(SCHEMA)
        connection.execute("INSERT INTO Users VALUES (1, 'User')")
        connection.execute("INSERT INTO Shelves VALUES (1, 'A1', NULL)")
        connection.execute(
            """INSERT INTO Books (
                   isbn, title, owner_id, shelf_id
               ) VALUES (100, 'Book', 1, 1)"""
        )
        connection.execute(
            """INSERT INTO Loans (
                   loan_id, isbn, borrower_id, loan_date
               ) VALUES (1, '100', 1, CURRENT_TIMESTAMP)"""
        )
        connection.commit()
        migrate_user_entities(connection)
        connection.close()

        self.database_patch = patch("db.DATABASE", str(self.database))
        self.database_patch.start()
        app.config["TESTING"] = True
        self.client = app.test_client()

    def tearDown(self):
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_referenced_records_return_safe_conflict_responses(self):
        for path in ("/books/100", "/users/1", "/shelves/1"):
            with self.subTest(path=path):
                response = self.client.delete(path)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(
                    response.get_json(),
                    {
                        "description": (
                            "Database integrity constraint rejected request"
                        )
                    },
                )

    def test_invalid_book_owner_returns_conflict_and_rolls_back(self):
        response = self.client.post(
            "/books",
            json={"isbn": 101, "title": "Invalid", "owner_id": 404},
        )
        self.assertEqual(response.status_code, 409)

        connection = connect_database(self.database)
        try:
            self.assertIsNone(
                connection.execute(
                    "SELECT 1 FROM Books WHERE isbn = 101"
                ).fetchone()
            )
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
