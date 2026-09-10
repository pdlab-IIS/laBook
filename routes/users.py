from flask import Blueprint, request, jsonify, abort, make_response, render_template
from db import get_db

bp = Blueprint("users", __name__, url_prefix="/users")


@bp.route("/manage", methods=["GET"])
def manage_users_page():
    db = get_db()
    cursor = db.execute("""SELECT u.user_id, u.name, u.entity_type, u.can_own_books,
        (SELECT COUNT(*) FROM Books b WHERE b.owner_id=u.user_id) AS owned_count,
        (SELECT COUNT(*) FROM Loans l WHERE l.borrower_id=u.user_id AND l.return_date IS NULL) AS active_count,
        (SELECT COUNT(*) FROM Loans l WHERE l.borrower_id=u.user_id OR l.returner_id=u.user_id) AS history_count
        FROM Users u ORDER BY u.name, u.user_id""")
    entities = [dict(zip([c[0] for c in cursor.description], row)) for row in cursor.fetchall()]
    view = "all" if request.args.get("view") == "all" else "active"
    condition = "" if view == "all" else " WHERE l.return_date IS NULL"
    total = db.execute("SELECT COUNT(*) FROM Loans l" + condition).fetchone()[0]
    page_count = max(1, (total + 24) // 25)
    page = min(page_count, max(1, request.args.get("page", 1, type=int)))
    cursor = db.execute("""SELECT l.loan_id, l.isbn, b.title, borrower.name AS borrower_name,
        returner.name AS returner_name, l.loan_date, l.due_date, l.return_date
        FROM Loans l LEFT JOIN Books b ON b.isbn=l.isbn
        LEFT JOIN Users borrower ON borrower.user_id=l.borrower_id
        LEFT JOIN Users returner ON returner.user_id=l.returner_id""" + condition +
        " ORDER BY l.loan_date DESC, l.loan_id DESC LIMIT 25 OFFSET ?", ((page - 1) * 25,))
    loans = [dict(zip([c[0] for c in cursor.description], row)) for row in cursor.fetchall()]
    return render_template("manage_users.html", entities=entities, loans=loans, view=view,
                           total=total, page=page, page_count=page_count)


def reject(message, status=400):
    abort(make_response(jsonify(description=message), status))


def entity_fields(data, existing=None):
    existing = existing or {}
    kind = data.get("entity_type", existing.get("entity_type", "person"))
    eligible = data.get("can_own_books", existing.get("can_own_books", 0))
    name = data.get("user_name", data.get("name", existing.get("name")))
    if not isinstance(name, str) or not name.strip():
        reject("Name is required")
    if kind not in ("person", "organization"):
        reject("Invalid entity type")
    if type(eligible) not in (int, bool) or eligible not in (0, 1):
        reject("can_own_books must be a boolean")
    return name.strip(), kind, int(eligible)


@bp.route("", methods=["GET"])
def list_users():
    db = get_db()
    cursor = db.execute("SELECT * FROM Users")
    users = [
        dict(zip([col[0] for col in cursor.description], row))
        for row in cursor.fetchall()
    ]
    return jsonify(users)


@bp.route("/<int:user_id>", methods=["GET"])
def get_user(user_id):
    db = get_db()
    cursor = db.execute("SELECT * FROM Users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        abort(404, description="User not found")
    return jsonify(dict(zip([col[0] for col in cursor.description], row)))


@bp.route("/by_name/<name>", methods=["GET"])
def get_user_by_name(name):
    db = get_db()
    # Lending resolves people only, even when an organization shares the name.
    cursor = db.execute("SELECT * FROM Users WHERE name = ? AND entity_type='person' ORDER BY user_id", (name,))
    row = cursor.fetchone()
    if row is None:
        if db.execute("SELECT 1 FROM Users WHERE name=? AND entity_type='organization'", (name,)).fetchone():
            reject("貸出・返却には研究室・組織ではなく人物を指定してください。", 409)
        abort(404, description="User not found")
    return jsonify(dict(zip([col[0] for col in cursor.description], row)))


@bp.route("", methods=["POST"])
def add_user():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        reject("Expected a JSON object")
    name, kind, eligible = entity_fields(data)
    db = get_db()
    db.execute(
        "INSERT INTO Users (name, email, affiliation, entity_type, can_own_books) VALUES (?, ?, ?, ?, ?)",
        (name, data.get("email"), data.get("affiliation"), kind, eligible),
    )
    db.commit()
    user_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    return jsonify({"user_id": user_id}), 201


@bp.route("/<int:user_id>", methods=["PUT"])
def update_user(user_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        reject("Expected a JSON object")
    db = get_db()
    cursor = db.execute("SELECT * FROM Users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        abort(404, description="User not found")
    existing = dict(zip([column[0] for column in cursor.description], row))
    name, kind, eligible = entity_fields(data, existing)
    if not eligible and db.execute("SELECT 1 FROM Books WHERE owner_id=? LIMIT 1", (user_id,)).fetchone():
        reject("先に所有している本のOwnerを変更・解除してください。", 409)
    if kind == "organization" and db.execute("SELECT 1 FROM Loans WHERE borrower_id=? OR returner_id=? LIMIT 1", (user_id, user_id)).fetchone():
        reject("貸出・返却履歴のある人物は組織に変更できません。", 409)
    db.execute(
        "UPDATE Users SET name=?, email=?, affiliation=?, entity_type=?, can_own_books=? WHERE user_id=?",
        (name, data.get("email", existing.get("email")), data.get("affiliation", existing.get("affiliation")), kind, eligible, user_id),
    )
    db.commit()
    return jsonify({"message": "User updated"})


@bp.route("/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    db = get_db()
    cursor = db.execute("SELECT * FROM Users WHERE user_id = ?", (user_id,))
    if cursor.fetchone() is None:
        abort(404, description="User not found")
    db.execute("DELETE FROM Users WHERE user_id = ?", (user_id,))
    db.commit()
    return jsonify({"message": "User deleted"})
