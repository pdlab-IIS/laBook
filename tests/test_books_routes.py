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
            CREATE TABLE Users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                entity_type TEXT NOT NULL DEFAULT 'person',
                can_own_books INTEGER NOT NULL DEFAULT 0
            );
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
            CREATE TABLE Loans (
                loan_id INTEGER PRIMARY KEY AUTOINCREMENT,
                isbn TEXT,
                borrower_id INTEGER,
                loan_date TEXT NOT NULL,
                due_date TEXT,
                return_date TEXT
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

    def test_owner_can_be_set_changed_preserved_and_cleared(self):
        self.db.executemany("INSERT INTO Users (user_id, name, can_own_books) VALUES (?, ?, 1)", [(1, "A"), (2, "B")])
        with mock.patch("routes.books.get_db", return_value=self.db):
            response = self.client.post("/books", json={"isbn": 101, "title": "Book", "owner_id": "1"})
            self.assertEqual(response.status_code, 201)
            for payload, expected in [
                ({"title": "Book", "owner_id": "2"}, 2),
                ({"title": "Renamed"}, 2),
                ({"title": "Book", "owner_id": ""}, None),
            ]:
                with self.subTest(payload=payload):
                    self.assertEqual(self.client.put("/books/101", json=payload).status_code, 200)
                    self.assertEqual(self.db.execute("SELECT owner_id FROM Books WHERE isbn=101").fetchone()[0], expected)

    def test_invalid_owner_is_rejected_without_changing_book(self):
        self.db.execute("INSERT INTO Users (user_id, name, can_own_books) VALUES (1, 'Owner', 1)")
        self.db.execute("INSERT INTO Books (isbn, title, owner_id) VALUES (101, 'Book', 1)")
        self.db.commit()
        with mock.patch("routes.books.get_db", return_value=self.db):
            for owner in (404, -1, "invalid", 1.5, True, False, str(2**63), "9" * 100):
                with self.subTest(owner=owner):
                    response = self.client.put("/books/101", json={"title": "Changed", "owner_id": owner})
                    self.assertEqual(response.status_code, 409)
                    self.assertIn("description", response.get_json())
                    self.assertEqual(self.db.execute("SELECT title, owner_id FROM Books WHERE isbn=101").fetchone(), ("Book", 1))

    def test_owner_selector_is_only_rendered_on_manage_pages(self):
        from app import app

        self.db.execute("INSERT INTO Users (user_id, name, can_own_books) VALUES (1, '<Owner>', 1)")
        self.db.execute("INSERT INTO Books (isbn, title, owner_id) VALUES (101, 'Book', 1)")
        with mock.patch("routes.books.get_db", return_value=self.db):
            client = app.test_client()
            for path in ("/books/manage", "/books/manage?isbn=101"):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                self.assertIn('<select name="owner_id" id="owner_id">', html)
                self.assertIn('<option value="">未設定</option>', html)
                self.assertIn('&lt;Owner&gt; (ID: 1)', html)
                self.assertNotIn('<Owner>', html)
                if "isbn=" in path:
                    self.assertIn('<option value="1" selected>', html)
            self.assertNotIn('id="owner_id"', client.get('/').get_data(as_text=True))

    def test_manage_owner_selector_allows_no_registered_users(self):
        from app import app

        with mock.patch("routes.books.get_db", return_value=self.db):
            response = app.test_client().get("/books/manage")
        self.assertEqual(response.status_code, 200)
        self.assertIn('<option value="">未設定</option>', response.get_data(as_text=True))

    def test_inventory_add_returns_created_shelf_for_immediate_rendering(self):
        with mock.patch("routes.books.get_db", return_value=self.db):
            response = self.client.post(
                "/books",
                json={
                    "isbn": "9780000000002",
                    "title": "Inventory book",
                    "shelf_code": "NEW-LOCATION",
                },
            )

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(data["shelf_code"], "NEW-LOCATION")
        self.assertIsInstance(data["shelf_id"], int)
        shelf_id = self.db.execute(
            "SELECT shelf_id FROM Books WHERE isbn = ?",
            ("9780000000002",),
        ).fetchone()[0]
        self.assertEqual(data["shelf_id"], shelf_id)

    def test_inventory_move_returns_created_shelf_for_immediate_rendering(self):
        self.db.execute(
            "INSERT INTO Books (isbn, title) VALUES (?, ?)",
            ("9780000000003", "Moved book"),
        )
        self.db.commit()

        with mock.patch("routes.books.get_db", return_value=self.db):
            response = self.client.put(
                "/books/move/9780000000003",
                json={"shelf_code": "MOVE-LOCATION"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["shelf_code"], "MOVE-LOCATION")
        self.assertIsInstance(data["shelf_id"], int)
        shelf_id = self.db.execute(
            "SELECT shelf_id FROM Books WHERE isbn = ?",
            ("9780000000003",),
        ).fetchone()[0]
        self.assertEqual(data["shelf_id"], shelf_id)

    def test_borrowed_filter_applies_before_pagination(self):
        self.db.execute("INSERT INTO Users (name) VALUES ('Borrower')")
        self.db.executemany(
            "INSERT INTO Books (isbn, title) VALUES (?, ?)",
            [(1000 + index, f"Book {index:02d}") for index in range(30)],
        )
        self.db.executemany(
            """INSERT INTO Loans (isbn, borrower_id, loan_date, return_date)
               VALUES (?, 1, '2026-09-01', ?)""",
            [
                (1005, None),
                (1010, "2026-09-02"),
                (1029, None),
            ],
        )
        self.db.commit()

        with mock.patch("routes.books.get_db", return_value=self.db):
            response = self.client.get(
                "/books?status=borrowed&sort=isbn&order=asc&limit=25&offset=0"
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["total_count"], 2)
        self.assertEqual([book["isbn"] for book in data["books"]], [1005, 1029])

    def test_location_name_filter_applies_before_pagination_and_count(self):
        self.db.execute("INSERT INTO Shelves VALUES (1, 'A1', '')")
        self.db.executemany(
            "INSERT INTO Books (isbn, title, shelf_id) VALUES (?, ?, ?)",
            [(1000 + i, f"Book {i}", 1) for i in range(30)]
            + [(2000, 'A1 appears in title only', None)],
        )
        with mock.patch("routes.books.get_db", return_value=self.db):
            response = self.client.get(
                "/books?keyword=A1&sort=isbn&order=asc&limit=25&offset=25"
            ).get_json()
            count = self.client.get("/books?keyword=A1&count_only=1").get_json()
        self.assertEqual(response["total_count"], 30)
        self.assertEqual([book["isbn"] for book in response["books"]], list(range(1025, 1030)))
        self.assertEqual(count["count"], 30)

    def test_location_search_composes_with_status_and_keeps_text_search(self):
        self.db.execute("INSERT INTO Shelves VALUES (1, 'A1', '')")
        self.db.execute("INSERT INTO Users (user_id, name) VALUES (1, 'Reader')")
        self.db.executemany(
            "INSERT INTO Books (isbn, title, shelf_id) VALUES (?, ?, ?)",
            [(1000, 'First', 1), (1001, 'Second', 1), (2000, 'Ordinary text', None)],
        )
        self.db.execute(
            "INSERT INTO Loans (isbn, borrower_id, loan_date) VALUES (1001, 1, '2026-09-07')"
        )
        with mock.patch("routes.books.get_db", return_value=self.db):
            borrowed = self.client.get("/books?keyword=A1&status=borrowed&sort=isbn").get_json()
            text = self.client.get("/books?keyword=Ordinary&sort=isbn").get_json()
            empty = self.client.get("/books?keyword=unknown-location&sort=isbn").get_json()
        self.assertEqual([book["isbn"] for book in borrowed["books"]], [1001])
        self.assertEqual([book["isbn"] for book in text["books"]], [2000])
        self.assertEqual(empty["total_count"], 0)


if __name__ == "__main__":
    unittest.main()
