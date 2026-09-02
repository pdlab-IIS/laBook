from flask import (
    Blueprint,
    request,
    jsonify,
    abort,
    render_template,
    redirect,
    url_for,
    Response,
)
from db import get_db
import fetch_book_info
import logging, os, sqlite3
from datetime import datetime

bp = Blueprint("books", __name__, url_prefix="/books")
logger = logging.getLogger(__name__)


def get_book_status(db, isbn):
    cursor = db.execute(
        "SELECT 1 FROM Loans WHERE isbn = ? AND return_date IS NULL LIMIT 1", (isbn,)
    )
    if cursor.fetchone() is None:
        return None
    else:
        user = db.execute(
            "SELECT borrower_id FROM Loans WHERE isbn = ? AND return_date IS NULL LIMIT 1",
            (isbn,),
        ).fetchone()
        if user:
            user_id = user[0]
            cursor = db.execute("SELECT name FROM Users WHERE user_id = ?", (user_id,))
            borrower = cursor.fetchone()
            if borrower:
                return f"{borrower[0]}"
        else:
            return "Error: No borrower found"


def get_or_create_shelf_id(db, shelf_code, location_description=None):
    """Return a shelf id without making a nested HTTP request to this app."""
    normalized_code = str(shelf_code).strip()
    if not normalized_code:
        return None

    row = db.execute(
        "SELECT shelf_id FROM Shelves WHERE shelf_code = ?",
        (normalized_code,),
    ).fetchone()
    if row:
        return row[0]

    db.execute(
        """INSERT OR IGNORE INTO Shelves (shelf_code, location_description)
           VALUES (?, ?)""",
        (normalized_code, location_description or ""),
    )
    row = db.execute(
        "SELECT shelf_id FROM Shelves WHERE shelf_code = ?",
        (normalized_code,),
    ).fetchone()
    if row is None:
        raise RuntimeError("Failed to create shelf")
    return row[0]


def normalize_owner_id(owner_id):
    """Convert the historical zero sentinel to a nullable foreign key."""
    if owner_id in (None, "", 0, "0"):
        return None
    return owner_id


@bp.route("", methods=["GET"])
def list_books():
    db = get_db()
    sort_key = request.args.get("sort", "updatedtime")
    order = request.args.get("order", "desc")
    offset = request.args.get("offset", type=int, default=0)
    limit = request.args.get("limit", type=int, default=100)
    keyword = request.args.get("keyword", "").strip()
    status_filter = request.args.get("status", "").strip()
    conditions = []
    filter_params = []

    if keyword:
        if keyword.startswith("shelf_id:"):
            conditions.append("Books.shelf_id = ?")
            filter_params.append(keyword.split(":", 1)[1])
        else:
            conditions.append(
                "(Books.title LIKE ? OR Books.author LIKE ? "
                "OR Books.publisher LIKE ? OR Books.isbn LIKE ?)"
            )
            kw = f"%{keyword}%"
            filter_params.extend([kw, kw, kw, keyword])

    if status_filter == "borrowed":
        conditions.append(
            "EXISTS ("
            "SELECT 1 FROM Loans "
            "WHERE Loans.isbn = Books.isbn AND Loans.return_date IS NULL"
            ")"
        )

    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    count_only = request.args.get("count_only")
    if count_only:
        sql = "SELECT COUNT(*) FROM Books" + where_clause
        count = db.execute(sql, filter_params).fetchone()[0]
        return jsonify({"count": count})

    # --- 総件数取得 ---
    count_sql = "SELECT COUNT(*) FROM Books" + where_clause
    total_count = db.execute(count_sql, filter_params).fetchone()[0]

    # --- 本リスト取得 ---
    valid_sort_keys = {
        "isbn",
        "title",
        "author",
        "publisher",
        "publication_date",
        "updatedtime",
        "shelf_id",
    }
    if sort_key not in valid_sort_keys:
        sort_key = "title"
    if order not in {"asc", "desc"}:
        order = "asc"

    sql = "SELECT Books.* FROM Books" + where_clause
    params = list(filter_params)
    sql += f" ORDER BY Books.{sort_key} {order.upper()} LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cursor = db.execute(sql, params)
    books = []
    columns = [col[0] for col in cursor.description]
    for row in cursor.fetchall():
        book = dict(zip(columns, row))
        book["status"] = get_book_status(db, book["isbn"])
        books.append(book)
    # --- ここで総数も返す ---
    return jsonify({"total_count": total_count, "books": books})


@bp.route("/<isbn>", methods=["GET"])
def get_book(isbn):
    db = get_db()
    cursor = db.execute("SELECT * FROM Books WHERE isbn = ?", (isbn,))
    row = cursor.fetchone()
    if row is None:
        abort(404, description="Book not found")
    book = dict(zip([col[0] for col in cursor.description], row))
    book["status"] = get_book_status(db, isbn)
    return jsonify(book), 200

def get_book_dict(isbn):
    db = get_db()
    cursor = db.execute("SELECT * FROM Books WHERE isbn = ?", (isbn,))
    row = cursor.fetchone()
    if row is None:
        return  None
    return dict(zip([col[0] for col in cursor.description], row))


@bp.route("", methods=["POST"])
def add_book():
    data = request.get_json(silent=True) or {}
    required = ["isbn", "title"]
    if not all(k in data for k in required):
        abort(400, description="Missing required fields")
    db = get_db()
    owner_id = normalize_owner_id(data.get("owner_id"))
    shelf_id = data.get("shelf_id")
    if not shelf_id and data.get("shelf_code"):
        shelf_id = get_or_create_shelf_id(
            db,
            data["shelf_code"],
            data.get("location_description"),
        )
    try:
        db.execute(
            "INSERT INTO Books (isbn, title, author, publisher, publication_date, cover_image_path, owner_id, comment, shelf_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                data["isbn"],
                data["title"],
                data.get("author"),
                data.get("publisher"),
                data.get("publication_date"),
                data.get("cover_image_path"),
                owner_id,
                data.get("comment"),
                shelf_id,
            ),
        )
        db.commit()
        logger.info("Book added: isbn=%s", data["isbn"])
    except sqlite3.IntegrityError:
        db.rollback()
        logger.warning("Book insert rejected by integrity constraint")
        abort(409, description="Book references invalid or duplicate data")
    return jsonify(
        {
            "message": "Book added",
            "shelf_id": shelf_id,
            "shelf_code": data.get("shelf_code"),
        }
    ), 201


@bp.route("/<isbn>", methods=["PUT"])
def update_book(isbn):
    data = request.get_json()
    db = get_db()
    cursor = db.execute("SELECT * FROM Books WHERE isbn = ?", (isbn,))
    if cursor.fetchone() is None:
        abort(404, description="Book not found")
    owner_id = normalize_owner_id(data.get("owner_id"))
    shelf_id = data.get("shelf_id")
    if not shelf_id and data.get("shelf_code"):
        shelf_id = get_or_create_shelf_id(
            db,
            data["shelf_code"],
            data.get("location_description"),
        )
    db.execute(
        """UPDATE Books SET title=?, author=?, publisher=?, publication_date=?, cover_image_path=?, owner_id=?, comment=?, shelf_id=?
           WHERE isbn=?""",
        (
            data.get("title"),
            data.get("author"),
            data.get("publisher"),
            data.get("publication_date"),
            data.get("cover_image_path"),
            owner_id,
            data.get("comment"),
            shelf_id,
            isbn,
        ),
    )
    db.commit()
    logger.info("Book updated: isbn=%s", isbn)
    return jsonify(
        {
            "message": "Book updated",
            "shelf_id": shelf_id,
            "shelf_code": data.get("shelf_code"),
        }
    )


@bp.route("/move/<isbn>", methods=["PUT"])
def move_book(isbn):
    data = request.get_json()
    db = get_db()
    cursor = db.execute("SELECT * FROM Books WHERE isbn = ?", (isbn,))
    if cursor.fetchone() is None:
        abort(404, description="Book not found")
    shelf_id = data.get("shelf_id")
    if not shelf_id and data.get("shelf_code"):
        shelf_id = get_or_create_shelf_id(
            db,
            data["shelf_code"],
            data.get("location_description"),
        )
    db.execute(
        """UPDATE Books SET shelf_id=? WHERE isbn=?""",
        (
            shelf_id,
            isbn,
        ),
    )
    db.commit()
    logger.info("Book moved: isbn=%s", isbn)
    return jsonify(
        {
            "message": "Book updated",
            "shelf_id": shelf_id,
            "shelf_code": data.get("shelf_code"),
        }
    )


@bp.route("/<isbn>", methods=["DELETE"])
def delete_book(isbn):
    db = get_db()
    cursor = db.execute("SELECT * FROM Books WHERE isbn = ?", (isbn,))
    if cursor.fetchone() is None:
        abort(404, description="Book not found")
    db.execute("DELETE FROM Books WHERE isbn = ?", (isbn,))
    db.commit()
    logger.info(f"Book deleted: {isbn}")
    return jsonify({"message": "Book deleted"})


@bp.route("/api/fetch_book_info/<isbn>")
def api_fetch_book_info(isbn):
    info = fetch_book_info.fetch_book_info(isbn)
    if info:
        return jsonify(info)
    else:
        return jsonify({"error": "No book info found"}), 404

@bp.route("/<isbn>/cover", methods=["POST"])
def upload_cover(isbn):
    """
    Upload or replace the cover image for a book.
    Accepts multipart/form-data with a file field named 'cover'.
    """
    if 'cover' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['cover']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if not file.filename.lower().endswith('.jpg') and not file.filename.lower().endswith('.jpeg'):
        return jsonify({"error": "Only .jpg files are allowed"}), 400

    covers_dir = os.path.join(os.path.dirname(__file__), '..', 'covers')
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    save_filename = f"{isbn}_{timestamp}.jpg"
    covers_dir = os.path.abspath(covers_dir)
    os.makedirs(covers_dir, exist_ok=True)
    save_path = os.path.join(covers_dir, save_filename)
    file.save(save_path)
    logger.info(f"cover image added: {save_path}")
    return jsonify({"message": "Cover image uploaded", "cover_image_path": f"covers/{save_filename}"})

@bp.route("/manage", methods=["GET"])
def manage_book_page():
    import requests
    from flask import current_app

    error = None
    book = None
    mode = "add"
    isbn = request.args.get("isbn")
    location_code_override = request.args.get("location_code_override")

    if isbn:
        book = get_book_dict(isbn)
        if book != None:
            mode = "edit"
            db= get_db()
            book["status"] = get_book_status(db, isbn)
        else:
            import fetch_book_info

            info = fetch_book_info.fetch_book_info(isbn)
            if info:
                book = info
            else:
                book = {"isbn": isbn}

    return render_template(
        "manage_book.html",
        book=book,
        error=error,
        mode=mode,
        location_code_override=location_code_override,
    )
