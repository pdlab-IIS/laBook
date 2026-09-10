import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from db import close_connection, connect_database
from routes.loans import (
    ActiveLoanExistsError,
    LoanAlreadyReturnedError,
    bp,
    create_active_loan,
    return_active_loan,
)


SCHEMA = """
CREATE TABLE Users (
    user_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE Books (
    isbn INTEGER PRIMARY KEY,
    title TEXT NOT NULL
);
CREATE TABLE Loans (
    loan_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
CREATE UNIQUE INDEX one_active_loan_per_isbn
ON Loans(isbn) WHERE return_date IS NULL;
"""


class LoanServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "library.db"
        connection = connect_database(self.database)
        connection.executescript(SCHEMA)
        connection.execute("INSERT INTO Users VALUES (1, 'Borrower')")
        connection.executemany(
            "INSERT INTO Books VALUES (?, ?)",
            [(100, "First"), (101, "Second"), (102, "Third")],
        )
        connection.commit()
        connection.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_rejects_a_second_active_loan(self):
        connection = connect_database(self.database)
        try:
            create_active_loan(connection, 100, 1)
            with self.assertRaises(ActiveLoanExistsError):
                create_active_loan(connection, 100, 1)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM Loans").fetchone()[0],
                1,
            )
        finally:
            connection.close()

    def test_foreign_key_rejects_an_unknown_borrower(self):
        connection = connect_database(self.database)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                create_active_loan(connection, 102, 404)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM Loans").fetchone()[0],
                0,
            )
        finally:
            connection.close()

    def test_return_is_atomic_and_cannot_be_repeated(self):
        connection = connect_database(self.database)
        try:
            loan_id = create_active_loan(connection, 100, 1)
            return_active_loan(connection, loan_id, 1)
            with self.assertRaises(LoanAlreadyReturnedError):
                return_active_loan(connection, loan_id, 1)
            self.assertIsNotNone(
                connection.execute(
                    "SELECT return_date FROM Loans WHERE loan_id = ?",
                    (loan_id,),
                ).fetchone()[0]
            )
        finally:
            connection.close()

    def test_concurrent_attempts_create_only_one_active_loan(self):
        barrier = threading.Barrier(2)

        def attempt():
            connection = connect_database(self.database)
            try:
                barrier.wait()
                try:
                    create_active_loan(connection, 101, 1)
                    return "created"
                except ActiveLoanExistsError:
                    return "conflict"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _index: attempt(), range(2)))

        self.assertEqual(sorted(results), ["conflict", "created"])
        connection = connect_database(self.database)
        try:
            self.assertEqual(
                connection.execute(
                    """SELECT COUNT(*) FROM Loans
                       WHERE isbn = 101 AND return_date IS NULL"""
                ).fetchone()[0],
                1,
            )
        finally:
            connection.close()


class LoanRouteTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "library.db"
        connection = connect_database(self.database)
        connection.executescript(SCHEMA)
        connection.execute("INSERT INTO Users VALUES (1, 'Borrower')")
        connection.executemany(
            "INSERT INTO Books VALUES (?, ?)",
            [(100, "Book"), (101, "Another book")],
        )
        connection.commit()
        connection.close()

        self.database_patch = patch("db.DATABASE", str(self.database))
        self.database_patch.start()
        app = Flask(__name__)
        app.config["TESTING"] = True
        app.register_blueprint(bp)
        app.teardown_appcontext(close_connection)
        self.client = app.test_client()

    def tearDown(self):
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_route_returns_conflict_for_duplicate_or_invalid_user(self):
        response = self.client.post(
            "/loans",
            json={"isbn": 100, "borrower_id": 1},
        )
        self.assertEqual(response.status_code, 201)

        duplicate = self.client.post(
            "/loans",
            json={"isbn": 100, "borrower_id": 1},
        )
        self.assertEqual(duplicate.status_code, 409)

        invalid_user = self.client.post(
            "/loans",
            json={"isbn": 101, "borrower_id": 404},
        )
        self.assertEqual(invalid_user.status_code, 409)

    def test_route_returns_not_found_for_missing_book(self):
        response = self.client.post(
            "/loans",
            json={"isbn": 999, "borrower_id": 1},
        )
        self.assertEqual(response.status_code, 404)

    def test_route_rejects_repeated_return(self):
        created = self.client.post(
            "/loans",
            json={"isbn": 100, "borrower_id": 1},
        )
        loan_id = created.get_json()["loan_id"]

        returned = self.client.post(
            f"/loans/{loan_id}",
            json={"returner_id": 1},
        )
        self.assertEqual(returned.status_code, 200)

        repeated = self.client.post(
            f"/loans/{loan_id}",
            json={"returner_id": 1},
        )
        self.assertEqual(repeated.status_code, 409)


if __name__ == "__main__":
    unittest.main()
