from flask import Blueprint, request, jsonify, abort
from db import get_db

bp = Blueprint("loans", __name__, url_prefix="/loans")


@bp.route("", methods=["GET"])
def list_loans():
    db = get_db()
    cursor = db.execute("SELECT * FROM Loans")
    loans = [
        dict(zip([col[0] for col in cursor.description], row))
        for row in cursor.fetchall()
    ]
    return jsonify(loans)


@bp.route("/<int:loan_id>", methods=["GET"])
def get_loan(loan_id):
    db = get_db()
    cursor = db.execute("SELECT * FROM Loans WHERE loan_id = ?", (loan_id,))
    row = cursor.fetchone()
    if row is None:
        abort(404, description="Loan not found")
    return jsonify(dict(zip([col[0] for col in cursor.description], row)))


@bp.route("", methods=["POST"])
def add_loan():
    data = request.get_json()
    required = ["isbn", "borrower_id"]
    if not all(k in data for k in required):
        abort(400, description="Missing required fields")
    db = get_db()
    db.execute(
        "INSERT INTO Loans (isbn, borrower_id, returner_id, loan_date, due_date, return_date) VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?)",
        (
            data["isbn"],
            data["borrower_id"],
            data.get("returner_id"),
            data.get("due_date"),
            data.get("return_date"),
        ),
    )
    db.commit()
    return jsonify({"message": "Loan created"}), 201


@bp.route("/<int:loan_id>", methods=["POST"])
def end_loan(loan_id):
    data = request.get_json()
    db = get_db()
    cursor = db.execute("SELECT * FROM Loans WHERE loan_id = ?", (loan_id,))
    if cursor.fetchone() is None:
        abort(404, description="Loan not found")
    db.execute(
        "UPDATE Loans SET  returner_id=?, return_date= CURRENT_TIMESTAMP WHERE loan_id=?",
        (data.get("returner_id"), loan_id),
    )
    db.commit()
    return jsonify({"message": "Loan updated"})


@bp.route("/<int:loan_id>", methods=["DELETE"])
def delete_loan(loan_id):
    db = get_db()
    cursor = db.execute("SELECT * FROM Loans WHERE loan_id = ?", (loan_id,))
    if cursor.fetchone() is None:
        abort(404, description="Loan not found")
    db.execute("DELETE FROM Loans WHERE loan_id = ?", (loan_id,))
    db.commit()
    return jsonify({"message": "Loan deleted"})


@bp.route("/activeLoan/<int:isbn>", methods=["POST"])
def active_loan(isbn):
    db = get_db()
    cursor = db.execute(
        "SELECT * FROM Loans WHERE isbn = ? AND return_date IS NULL LIMIT 1", (isbn,)
    )
    row = cursor.fetchone()
    if row is None:
        abort(404, description="Loan not found")

    return jsonify(dict(zip([col[0] for col in cursor.description], row))), 200
