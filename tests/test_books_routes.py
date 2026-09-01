import sqlite3
import unittest
from unittest import mock

from flask import Flask

from routes.books import bp


class BookRouteTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript(
            """
            CREATE TABLE Shelves (
                shelf_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                owner_id INTEGER DEFAULT NULL,
                comment TEXT,
                shelf_id INTEGER
            );
            """
        )
        self.app = Flask(__name__)
        self.app.register_blueprint(bp)
        self.client = self.app.test_client()

    def tearDown(self):
        self.db.close()

    def test_add_book_converts_zero_owner_to_null(self):
        with mock.patch("routes.books.get_db", return_value=self.db):
            response = self.client.post(
                "/books",
                json={
                    "isbn": "9780000000001",
                    "title": "Test book",
                    "owner_id": "0",
                },
            )

        self.assertEqual(response.status_code, 201)
        owner_id = self.db.execute(
            "SELECT owner_id FROM Books WHERE isbn = ?",
            ("9780000000001",),
        ).fetchone()[0]
        self.assertIsNone(owner_id)


if __name__ == "__main__":
    unittest.main()
