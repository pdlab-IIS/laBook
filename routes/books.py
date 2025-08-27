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
import requests, logging, os

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


def get_or_create_shelf_id(shelf_code, shelf_name=None, location_description=None):
    from flask import current_app

    api_url = f"http://localhost:5000/shelves/by_code/{shelf_code}"
    try:
        resp = requests.get(api_url)
        if resp.status_code == 200:
            return resp.json()["shelf_id"]
    except Exception:
        pass
    api_url = f"http://localhost:5000/shelves"
    payload = {
        "shelf_code": shelf_code,
        "shelf_name": shelf_name or shelf_code,
        "location_description": location_description or "",
    }
    resp = requests.post(api_url, json=payload)
    if resp.status_code in (200, 201):
        return resp.json()["shelf_id"]
    else:
        raise Exception("Failed to create shelf")


@bp.route("", methods=["GET"])
def list_books():
    db = get_db()
    sort_key = request.args.get("sort", "updatedtime")
    order = request.args.get("order", "desc")
    offset = request.args.get("offset", type=int, default=0)
    limit = request.args.get("limit", type=int, default=100)
    keyword = request.args.get("keyword", "").strip()
    count_only = request.args.get("count_only")
    if count_only:
        sql = "SELECT COUNT(*) FROM Books"
        params = []
        if keyword:
            sql += " WHERE title LIKE ? OR author LIKE ? OR publisher LIKE ?"
            kw = f"%{keyword}%"
            params = [kw, kw, kw]
        count = db.execute(sql, params).fetchone()[0]
        return jsonify({"count": count})

    # --- 総件数取得 ---
    count_sql = "SELECT COUNT(*) FROM Books"
    count_params = []
    if keyword:
        if keyword.startswith("shelf_id:"):
            count_sql += " WHERE shelf_id = ? "
            count_params.append(keyword.split(":", 1)[1])
        else:
            count_sql += " WHERE title LIKE ? OR author LIKE ? OR publisher LIKE ? OR isbn LIKE ? "
            kw = f"%{keyword}%"
            count_params.extend([kw, kw, kw, keyword])
    total_count = db.execute(count_sql, count_params).fetchone()[0]

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

    sql = "SELECT * FROM Books"
    params = []
    if keyword:
        if keyword.startswith("shelf_id:"):
            sql += " WHERE shelf_id = ? "
            params.append(keyword.split(":", 1)[1])
        else:
            sql += " WHERE title LIKE ? OR author LIKE ? OR publisher LIKE ? OR isbn LIKE ? "
            kw = f"%{keyword}%"
            params.extend([kw, kw, kw, keyword])
    sql += f" ORDER BY {sort_key} {order.upper()} LIMIT ? OFFSET ?"
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
    data = request.get_json()
    required = ["isbn", "title"]
    if not all(k in data for k in required):
        abort(400, description="Missing required fields")
    db = get_db()
    shelf_id = data.get("shelf_id")
    if not shelf_id and data.get("shelf_code"):
        shelf_id = get_or_create_shelf_id(
            data["shelf_code"], data.get("shelf_name"), data.get("location_description")
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
                data.get("owner_id"),
                data.get("comment"),
                shelf_id,
            ),
        )
        db.commit()
        logger.info(f"Book added: {data}")
    except Exception:
        abort(409, description=Exception)
        logger.error(f"Failed to add book: {data}")
    return jsonify({"message": "Book added"}), 201


@bp.route("/<isbn>", methods=["PUT"])
def update_book(isbn):
    data = request.get_json()
    db = get_db()
    cursor = db.execute("SELECT * FROM Books WHERE isbn = ?", (isbn,))
    if cursor.fetchone() is None:
        abort(404, description="Book not found")
    shelf_id = data.get("shelf_id")
    if not shelf_id and data.get("shelf_code"):
        shelf_id = get_or_create_shelf_id(
            data["shelf_code"], data.get("shelf_name"), data.get("location_description")
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
            data.get("owner_id"),
            data.get("comment"),
            shelf_id,
            isbn,
        ),
    )
    db.commit()
    logger.info(f"Book updated: {data}")
    return jsonify({"message": "Book updated"})


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
            data["shelf_code"], data.get("shelf_name"), data.get("location_description")
        )
    db.execute(
        """UPDATE Books SET shelf_id=? WHERE isbn=?""",
        (
            shelf_id,
            isbn,
        ),
    )
    db.commit()
    logger.info(f"Book moved: {data}")
    return jsonify({"message": "Book updated"})


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
    covers_dir = os.path.abspath(covers_dir)
    os.makedirs(covers_dir, exist_ok=True)
    save_path = os.path.join(covers_dir, f"{isbn}.jpg")
    file.save(save_path)
    logger.info(f"cover image added: {save_path}")
    return jsonify({"message": "Cover image uploaded", "cover_image_path": f"covers/{isbn}.jpg"})

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
