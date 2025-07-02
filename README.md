# laBook

This project is a web application for managing and lending laboratory books.

---

## 📚 Table Structure

### `Books`

| Column Name        | Type    | Constraint                       | Description        |
| ------------------ | ------- | -------------------------------- | ------------------ |
| `isbn`             | INTEGER | PRIMARY KEY                      | Book ISBN (unique) |
| `title`            | TEXT    | NOT NULL                         | Title              |
| `author`           | TEXT    |                                  | Author             |
| `publisher`        | TEXT    |                                  | Publisher          |
| `publication_date` | TEXT    |                                  | Publication date   |
| `cover_image_path` | TEXT    |                                  | Cover image path   |
| `owner_id`         | INTEGER | FOREIGN KEY → `Users.user_id`    | Owner              |
| `comment`          | TEXT    |                                  | Notes              |
| `shelf_id`         | INTEGER | FOREIGN KEY → `Shelves.shelf_id` | Shelf              |

---

### `Shelves`

| Column Name            | Type    | Constraint                | Description          |
| ---------------------- | ------- | ------------------------- | -------------------- |
| `shelf_id`             | INTEGER | PRIMARY KEY AUTOINCREMENT | Shelf ID             |
| `shelf_code`           | TEXT    | UNIQUE NOT NULL           | Shelf code (e.g. A1) |
| `location_description` | TEXT    |                           | Shelf description    |

---

### `Users`

| Column Name   | Type    | Constraint                | Description   |
| ------------- | ------- | ------------------------- | ------------- |
| `user_id`     | INTEGER | PRIMARY KEY AUTOINCREMENT | User ID       |
| `name`        | TEXT    | NOT NULL                  | Name          |
| `email`       | TEXT    |                           | Email address |
| `affiliation` | TEXT    |                           | Affiliation   |

---

### `Loans`

| Column Name   | Type    | Constraint                  | Description                   |
| ------------- | ------- | --------------------------- | ----------------------------- |
| `loan_id`     | INTEGER | PRIMARY KEY AUTOINCREMENT   | Loan ID                       |
| `isbn`        | TEXT    | FOREIGN KEY → `Books.isbn`    | Loaned book                   |
| `borrower_id` | INTEGER | FOREIGN KEY → `Users.user_id` | Borrower                      |
| `returner_id` | INTEGER | FOREIGN KEY → `Users.user_id` | Returner                      |
| `loan_date`   | TEXT    | NOT NULL                    | Loan date                     |
| `due_date`    | TEXT    |                             | Due date                      |
| `return_date` | TEXT    |                             | Return date (NULL if not yet) |

---

## 📡 REST API

Implemented with Flask. All data is exchanged in JSON.

### Books

| Method | Endpoint                            | Description                       |
| ------ | ----------------------------------- | --------------------------------- |
| GET    | `/books`                            | List all books (with status)      |
| GET    | `/books/<isbn>`                     | Book details (with status)        |
| POST   | `/books`                            | Add a book                        |
| PUT    | `/books/<isbn>`                     | Update book information           |
| DELETE | `/books/<isbn>`                     | Delete a book                     |
| GET    | `/books/api/fetch_book_info/<isbn>` | Fetch book info from external API |

**Book JSON Example:**
```json
{
  "isbn": "9781234567890",
  "title": "Book Title",
  "author": "Author Name",
  "publisher": "Publisher",
  "publication_date": "2020-01-01",
  "cover_image_path": "/covers/9781234567890.jpg",
  "owner_id": 1,
  "comment": "Some notes",
  "shelf_id": 1,
  "status": "<name(not user_id)>" //or null
}
```
---

### Shelves

| Method | Endpoint                        | Description                |
| ------ | ------------------------------- | -------------------------- |
| GET    | `/shelves`                      | List shelves               |
| GET    | `/shelves/<shelf_id>`           | Shelf details              |
| GET    | `/shelves/by_code/<shelf_code>` | Get shelf_id by shelf_code |
| POST   | `/shelves`                      | Add shelf                  |
| PUT    | `/shelves/<shelf_id>`           | Update shelf               |
| DELETE | `/shelves/<shelf_id>`           | Delete shelf               |

- All operations use `shelf_id` as the key.
- When adding, duplicate `shelf_code` is not allowed.

---

### Users

| Method | Endpoint      | Description      |
| ------ | ------------- | ---------------- |
| GET    | `/users`      | List users       |
| GET    | `/users/<id>` | User details     |
| POST   | `/users`      | Add user         |
| PUT    | `/users/<id>` | Update user info |
| DELETE | `/users/<id>` | Delete user      |

---

### Loans

| Method | Endpoint      | Description               |
| ------ | ------------- | ------------------------- |
| GET    | `/loans`      | List loans                |
| GET    | `/loans/<id>` | Loan details              |
| POST   | `/loans`      | New loan                  |
| PUT    | `/loans/<id>` | Update loan (e.g. return) |
| DELETE | `/loans/<id>` | Delete loan record        |

**Loan JSON Example:**
```json
{
  "isbn": "9781234567890",
  "borrower_id": 2,
  "returner_id": 3,
  "loan_date": "2024-06-19",
  "due_date": "2024-07-19",
  "return_date": null
}
```

---

## 📖 Book Add/Edit Page

- On `/books/manage`, entering an ISBN will:
  - Show the edit form if the book exists in the DB
  - Otherwise, fetch info from an external API and show the add form
- Both add and edit are handled on a single page
- Automatic detection and fetch on ISBN input

---

## 📷 Barcode Scanner

laBook includes a barcode scanner feature for quick book registration and management.

- Access the scanner page at `/scan/` or `/scan/<location_code>`.
- The scanner uses your device camera and QuaggaJS to read ISBN barcodes (EAN-13).
- When a valid ISBN is detected, you are redirected to the book management page with the ISBN and (optionally) the shelf location.
- The scanner UI is mobile-friendly and supports direct shelf assignment via the URL.

---

## 📦 Example Directory Structure

```
labook/
├── app.py
├── db.py
├── fetch_book_info.py
├── routes/
│   ├── __init__.py
│   ├── books.py
│   ├── shelves.py
│   ├── users.py
│   └── loans.py
├── static/
│   ├── book_form.js
│   ├── scanner.js
│   ├── quagga.min.js
│   └── style.css
├── templates/
│   ├── index.html
│   ├── manage_book.html
│   └── scan.html
├── library.db
├── README.md
```

---

## 🏁 Quick Start

1. Make venv and install dependencies  
   `pip install flask requests gunicorn`
1. Make some files and directories
   - `covers/`, `logs/`
   - `static/alert.mp3`, `static/newentry.mp3`,  `static/register.mp3`
   - [`static/quagga.min.js`](https://github.com/serratus/quaggaJS)
   - `keys.py`
     - ```  
        RAKUTEN_APP_ID = "***"
        GOOGLE_API_KEY = "***"
        ```
1. Start server  
   `python app.py`
1. Initialize DB  
   Access `/initdb`
1. Add/Edit books at `/books/manage`
1. Use the barcode scanner at `/scan/` for fast book registration.
