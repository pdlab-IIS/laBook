import sqlite3

from flask import Blueprint, abort, jsonify, request

from db import get_db

bp = Blueprint("loans", __name__, url_prefix="/loans")


class ActiveLoanExistsError(RuntimeError):
    """Raised when an ISBN already has an active loan."""


class LoanBookNotFoundError(RuntimeError):
    """Raised when a loan references a missing book."""


class LoanNotFoundError(RuntimeError):
    """Raised when a loan id does not exist."""


class LoanAlreadyReturnedError(RuntimeError):
    """Raised when a returned loan is returned again."""


def create_active_loan(db, isbn, borrower_id, due_date=None):
    """Create a loan atomically, serializing competing writers."""
    try:
        db.execute("BEGIN IMMEDIATE")
        if db.execute(
            "SELECT 1 FROM Books WHERE isbn = ?",
            (isbn,),
        ).fetchone() is None:
            raise LoanBookNotFoundError
        if db.execute(
            "SELECT 1 FROM Loans WHERE isbn = ? AND return_date IS NULL",
            (isbn,),
        ).fetchone():
            raise ActiveLoanExistsError

        cursor = db.execute(
            """INSERT INTO Loans (
                   isbn, borrower_id, returner_id,
                   loan_date, due_date, return_date
               ) VALUES (?, ?, NULL, CURRENT_TIMESTAMP, ?, NULL)""",
            (isbn, borrower_id, due_date),
        )
        db.commit()
        return cursor.lastrowid
    except Exception:
        db.rollback()
        raise


def return_active_loan(db, loan_id, returner_id):
    """Return one active loan in a single transaction."""
    try:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT return_date FROM Loans WHERE loan_id = ?",
            (loan_id,),
        ).fetchone()
        if row is None:
            raise LoanNotFoundError
        if row[0] is not None:
            raise LoanAlreadyReturnedError

        db.execute(
            """UPDATE Loans
               SET returner_id = ?, return_date = CURRENT_TIMESTAMP
               WHERE loan_id = ?""",
            (returner_id, loan_id),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise


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
    data = request.get_json(silent=True) or {}
    required = ["isbn", "borrower_id"]
    if not all(k in data for k in required):
        abort(400, description="Missing required fields")
    db = get_db()
    try:
        loan_id = create_active_loan(
            db,
            data["isbn"],
            data["borrower_id"],
            data.get("due_date"),
        )
    except LoanBookNotFoundError:
        abort(404, description="Book not found")
    except ActiveLoanExistsError:
        abort(409, description="Book already has an active loan")
    except sqlite3.IntegrityError:
        abort(409, description="Loan references an invalid user or book")
    return jsonify({"message": "Loan created", "loan_id": loan_id}), 201


@bp.route("/<int:loan_id>", methods=["POST"])
def end_loan(loan_id):
    data = request.get_json(silent=True) or {}
    db = get_db()
    try:
        return_active_loan(db, loan_id, data.get("returner_id"))
    except LoanNotFoundError:
        abort(404, description="Loan not found")
    except LoanAlreadyReturnedError:
        abort(409, description="Loan has already been returned")
    except sqlite3.IntegrityError:
        abort(409, description="Return references an invalid user")
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
