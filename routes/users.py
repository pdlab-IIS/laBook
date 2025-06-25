from flask import Blueprint, request, jsonify, abort
from db import get_db

bp = Blueprint("users", __name__, url_prefix="/users")


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
    cursor = db.execute("SELECT * FROM Users WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row is None:
        abort(404, description="User not found")
    return jsonify(dict(zip([col[0] for col in cursor.description], row)))


@bp.route("", methods=["POST"])
def add_user():
    data = request.get_json()
    if "user_name" not in data:
        abort(400, description="Missing required fields")
    db = get_db()
    db.execute(
        "INSERT INTO Users (name, email, affiliation) VALUES (?, ?, ?)",
        (data["user_name"], data.get("email"), data.get("affiliation")),
    )
    db.commit()
    user_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    return jsonify({"user_id": user_id}), 201


@bp.route("/<int:user_id>", methods=["PUT"])
def update_user(user_id):
    data = request.get_json()
    db = get_db()
    cursor = db.execute("SELECT * FROM Users WHERE user_id = ?", (user_id,))
    if cursor.fetchone() is None:
        abort(404, description="User not found")
    db.execute(
        "UPDATE Users SET name=?, email=?, affiliation=? WHERE user_id=?",
        (data.get("name"), data.get("email"), data.get("affiliation"), user_id),
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
