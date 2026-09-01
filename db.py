import os
import sqlite3
from flask import g

dbname = 'library.db'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, dbname)
BUSY_TIMEOUT_MS = 5000

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS Users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT,
    affiliation TEXT
);
CREATE TABLE IF NOT EXISTS Shelves (
    shelf_id INTEGER PRIMARY KEY AUTOINCREMENT,
    shelf_code TEXT NOT NULL UNIQUE,
    location_description TEXT
);
CREATE TABLE IF NOT EXISTS Books (
    isbn INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT,
    publisher TEXT,
    publication_date TEXT,
    cover_image_path TEXT,
    owner_id INTEGER DEFAULT NULL,
    comment TEXT,
    shelf_id INTEGER,
    updatedtime TEXT DEFAULT (CURRENT_TIMESTAMP),
    FOREIGN KEY(owner_id) REFERENCES Users(user_id) ON DELETE RESTRICT,
    FOREIGN KEY(shelf_id) REFERENCES Shelves(shelf_id) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS Loans (
    loan_id INTEGER PRIMARY KEY AUTOINCREMENT,
    isbn TEXT,
    borrower_id INTEGER,
    returner_id INTEGER,
    loan_date TEXT NOT NULL,
    due_date TEXT,
    return_date TEXT,
    FOREIGN KEY(isbn) REFERENCES Books(isbn) ON DELETE RESTRICT,
    FOREIGN KEY(borrower_id) REFERENCES Users(user_id) ON DELETE RESTRICT,
    FOREIGN KEY(returner_id) REFERENCES Users(user_id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_loan_per_isbn
ON Loans(isbn) WHERE return_date IS NULL;
CREATE TRIGGER IF NOT EXISTS update_books_updatedtime
AFTER UPDATE ON Books
FOR EACH ROW
BEGIN
    UPDATE Books SET updatedtime = CURRENT_TIMESTAMP WHERE isbn = OLD.isbn;
END;
"""


def connect_database(database_path=DATABASE):
    """Open an application connection with integrity enforcement enabled."""
    connection = sqlite3.connect(
        database_path,
        timeout=BUSY_TIMEOUT_MS / 1000,
    )
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    return connection

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = connect_database(DATABASE)
    return db

def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def apply_schema(connection):
    connection.executescript(SCHEMA_SQL)
    connection.commit()


def initialize_database(database_path=DATABASE):
    """Create a new database and refuse to overwrite an existing file."""
    descriptor = os.open(
        database_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    os.close(descriptor)
    try:
        connection = connect_database(database_path)
        try:
            apply_schema(connection)
        finally:
            connection.close()
    except Exception:
        os.unlink(database_path)
        raise


def init_db():
    db = get_db()
    apply_schema(db)
    return "Database initialized!"
