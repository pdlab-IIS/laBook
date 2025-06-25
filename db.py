import os
import sqlite3
from flask import g

dbname = 'library.db'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, dbname)

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db

def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    from db import get_db
    db = get_db()
    db.executescript("""
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
        owner_id INTEGER DEFAULT 0,
        comment TEXT,
        shelf_id INTEGER,
        updatedtime TEXT DEFAULT (CURRENT_TIMESTAMP),
        FOREIGN KEY(owner_id) REFERENCES Users(user_id),
        FOREIGN KEY(shelf_id) REFERENCES Shelves(shelf_id)
    );
    CREATE TABLE IF NOT EXISTS Loans (
        loan_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    CREATE TRIGGER IF NOT EXISTS update_books_updatedtime
    AFTER UPDATE ON Books
    FOR EACH ROW
    BEGIN
        UPDATE Books SET updatedtime = CURRENT_TIMESTAMP WHERE isbn = OLD.isbn;
    END;
    """)
    db.commit()
    return "Database initialized!"