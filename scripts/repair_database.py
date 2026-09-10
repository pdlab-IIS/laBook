"""Audit and repair known laBook foreign-key violations safely."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from db_backup import create_online_backup


OWNER_REPORT = "report"
OWNER_ARCHIVE_NULL = "archive-null"
LOAN_REPORT = "report"
LOAN_ARCHIVE_DELETE = "archive-delete"
ACTIVE_LOAN_REPORT = "report"
ACTIVE_LOAN_CREATE_INDEX = "create-unique-index"


class RepairPolicyError(RuntimeError):
    """Raised when an apply operation lacks an explicit repair policy."""


class RepairValidationError(RuntimeError):
    """Raised when a repair would leave the database inconsistent."""


@dataclass(frozen=True)
class DatabaseAudit:
    books: int
    users: int
    loans: int
    zero_owner_ids: int
    blank_owner_ids: int
    missing_owner_ids: int
    orphan_loans: int
    active_orphan_loans: int
    active_loans: int
    duplicate_active_isbns: int
    null_loan_isbns: int
    active_loan_unique_index: bool
    foreign_key_violations: int
    foreign_key_violations_by_relation: dict[str, int]
    archived_book_owners: int
    archived_orphan_loans: int

    @property
    def invalid_owner_ids(self):
        return self.zero_owner_ids + self.blank_owner_ids + self.missing_owner_ids

    def to_dict(self):
        result = asdict(self)
        result["invalid_owner_ids"] = self.invalid_owner_ids
        return result


def _count(connection, query, parameters=()):
    return connection.execute(query, parameters).fetchone()[0]


def _table_exists(connection, table_name):
    return bool(
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
    )


def _index_exists(connection, index_name):
    return bool(
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?",
            (index_name,),
        ).fetchone()
    )


def audit_database(connection):
    """Return aggregate integrity information without exposing book/user data."""
    zero_owner_ids = _count(
        connection,
        "SELECT COUNT(*) FROM Books WHERE owner_id = 0",
    )
    blank_owner_ids = _count(
        connection,
        """SELECT COUNT(*) FROM Books
           WHERE owner_id IS NOT NULL
             AND TRIM(CAST(owner_id AS TEXT)) = ''""",
    )
    missing_owner_ids = _count(
        connection,
        """SELECT COUNT(*)
           FROM Books AS book
           WHERE book.owner_id IS NOT NULL
             AND book.owner_id <> 0
             AND TRIM(CAST(book.owner_id AS TEXT)) <> ''
             AND NOT EXISTS (
                 SELECT 1 FROM Users AS user
                 WHERE user.user_id = book.owner_id
             )""",
    )
    orphan_loans = _count(
        connection,
        """SELECT COUNT(*)
           FROM Loans AS loan
           WHERE NOT EXISTS (
               SELECT 1 FROM Books AS book WHERE book.isbn = loan.isbn
           )""",
    )

    violations = list(connection.execute("PRAGMA foreign_key_check"))
    relation_counts = Counter(
        f"{row[0]}->{row[2]}" for row in violations
    )

    archived_book_owners = 0
    if _table_exists(connection, "BookOwnerRepairArchive"):
        archived_book_owners = _count(
            connection,
            "SELECT COUNT(*) FROM BookOwnerRepairArchive",
        )

    archived_orphan_loans = 0
    if _table_exists(connection, "LoansOrphanArchive"):
        archived_orphan_loans = _count(
            connection,
            "SELECT COUNT(*) FROM LoansOrphanArchive",
        )

    return DatabaseAudit(
        books=_count(connection, "SELECT COUNT(*) FROM Books"),
        users=_count(connection, "SELECT COUNT(*) FROM Users"),
        loans=_count(connection, "SELECT COUNT(*) FROM Loans"),
        zero_owner_ids=zero_owner_ids,
        blank_owner_ids=blank_owner_ids,
        missing_owner_ids=missing_owner_ids,
        orphan_loans=orphan_loans,
        active_orphan_loans=_count(
            connection,
            """SELECT COUNT(*)
               FROM Loans AS loan
               WHERE loan.return_date IS NULL
                 AND NOT EXISTS (
                     SELECT 1 FROM Books AS book WHERE book.isbn = loan.isbn
                 )""",
        ),
        active_loans=_count(
            connection,
            "SELECT COUNT(*) FROM Loans WHERE return_date IS NULL",
        ),
        duplicate_active_isbns=_count(
            connection,
            """SELECT COUNT(*) FROM (
                   SELECT isbn
                   FROM Loans
                   WHERE return_date IS NULL
                   GROUP BY isbn
                   HAVING COUNT(*) > 1
               )""",
        ),
        null_loan_isbns=_count(
            connection,
            "SELECT COUNT(*) FROM Loans WHERE isbn IS NULL",
        ),
        active_loan_unique_index=_index_exists(
            connection,
            "one_active_loan_per_isbn",
        ),
        foreign_key_violations=len(violations),
        foreign_key_violations_by_relation=dict(sorted(relation_counts.items())),
        archived_book_owners=archived_book_owners,
        archived_orphan_loans=archived_orphan_loans,
    )


def _create_owner_archive(connection):
    connection.execute(
        """CREATE TABLE IF NOT EXISTS BookOwnerRepairArchive (
               repair_id INTEGER PRIMARY KEY AUTOINCREMENT,
               isbn INTEGER NOT NULL,
               owner_id INTEGER NOT NULL,
               archive_reason TEXT NOT NULL,
               archived_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )


def _archive_and_null_invalid_owners(connection):
    _create_owner_archive(connection)
    archived = connection.execute(
        """INSERT INTO BookOwnerRepairArchive (
               isbn, owner_id, archive_reason
           )
           SELECT
               book.isbn,
               book.owner_id,
               CASE
                   WHEN book.owner_id = 0 THEN 'zero_sentinel'
                   WHEN TRIM(CAST(book.owner_id AS TEXT)) = '' THEN 'blank_value'
                   ELSE 'missing_user'
               END
           FROM Books AS book
           WHERE book.owner_id IS NOT NULL
             AND NOT EXISTS (
                 SELECT 1 FROM Users AS user
                 WHERE user.user_id = book.owner_id
             )"""
    ).rowcount
    updated = connection.execute(
        """UPDATE Books
           SET owner_id = NULL
           WHERE owner_id IS NOT NULL
             AND NOT EXISTS (
                 SELECT 1 FROM Users AS user
                 WHERE user.user_id = Books.owner_id
             )"""
    ).rowcount
    if archived != updated:
        raise RepairValidationError(
            f"Owner archive/update count mismatch: {archived} != {updated}"
        )
    return updated


def _create_loan_archive(connection):
    connection.execute(
        """CREATE TABLE IF NOT EXISTS LoansOrphanArchive (
               repair_id INTEGER PRIMARY KEY AUTOINCREMENT,
               source_loan_id INTEGER NOT NULL,
               isbn TEXT,
               borrower_id INTEGER,
               returner_id INTEGER,
               loan_date TEXT NOT NULL,
               due_date TEXT,
               return_date TEXT,
               archive_reason TEXT NOT NULL,
               archived_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )


def _archive_and_delete_orphan_loans(connection):
    _create_loan_archive(connection)
    archived = connection.execute(
        """INSERT INTO LoansOrphanArchive (
               source_loan_id, isbn, borrower_id, returner_id,
               loan_date, due_date, return_date, archive_reason
           )
           SELECT
               loan.loan_id, loan.isbn, loan.borrower_id, loan.returner_id,
               loan.loan_date, loan.due_date, loan.return_date, 'missing_book'
           FROM Loans AS loan
           WHERE NOT EXISTS (
               SELECT 1 FROM Books AS book WHERE book.isbn = loan.isbn
           )"""
    ).rowcount
    deleted = connection.execute(
        """DELETE FROM Loans
           WHERE NOT EXISTS (
               SELECT 1 FROM Books AS book WHERE book.isbn = Loans.isbn
           )"""
    ).rowcount
    if archived != deleted:
        raise RepairValidationError(
            f"Loan archive/delete count mismatch: {archived} != {deleted}"
        )
    return deleted


def _create_active_loan_unique_index(connection):
    existed = _index_exists(connection, "one_active_loan_per_isbn")
    connection.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS one_active_loan_per_isbn
           ON Loans(isbn) WHERE return_date IS NULL"""
    )
    return 0 if existed else 1


def _run_repair_transaction(
    connection,
    owner_policy,
    orphan_loan_policy,
    active_loan_policy,
    *,
    commit,
    require_clean,
):
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("BEGIN IMMEDIATE")
    try:
        owner_changes = 0
        if owner_policy == OWNER_ARCHIVE_NULL:
            owner_changes = _archive_and_null_invalid_owners(connection)

        loan_changes = 0
        if orphan_loan_policy == LOAN_ARCHIVE_DELETE:
            loan_changes = _archive_and_delete_orphan_loans(connection)

        index_changes = 0
        if active_loan_policy == ACTIVE_LOAN_CREATE_INDEX:
            index_changes = _create_active_loan_unique_index(connection)

        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RepairValidationError(f"Integrity check failed: {integrity}")

        result = audit_database(connection)
        if require_clean and result.foreign_key_violations:
            raise RepairValidationError(
                "Repair left "
                f"{result.foreign_key_violations} foreign-key violation(s)"
            )

        changes = {
            "book_owners_archived_and_nullified": owner_changes,
            "orphan_loans_archived_and_deleted": loan_changes,
            "active_loan_unique_index_created": index_changes,
        }
        if commit:
            connection.commit()
        else:
            connection.rollback()
        return result, changes
    except Exception:
        connection.rollback()
        raise


def _connect_read_only(database_path):
    return sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True)


def _preview(
    database_path,
    owner_policy,
    orphan_loan_policy,
    active_loan_policy,
):
    source = _connect_read_only(database_path)
    preview = sqlite3.connect(":memory:")
    try:
        source.backup(preview)
        return _run_repair_transaction(
            preview,
            owner_policy,
            orphan_loan_policy,
            active_loan_policy,
            commit=False,
            require_clean=False,
        )
    finally:
        preview.close()
        source.close()


def repair_database(
    database_path,
    *,
    apply=False,
    owner_policy=OWNER_REPORT,
    orphan_loan_policy=LOAN_REPORT,
    active_loan_policy=ACTIVE_LOAN_REPORT,
    confirm_archive_active_loans=False,
    backup_dir=None,
):
    """Preview or apply a repair and return a JSON-serializable report."""
    path = Path(database_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    source = _connect_read_only(path)
    try:
        before = audit_database(source)
    finally:
        source.close()

    if (
        before.duplicate_active_isbns
        and active_loan_policy == ACTIVE_LOAN_CREATE_INDEX
    ):
        raise RepairPolicyError(
            "Duplicate active loans exist; resolve them before creating the unique index"
        )

    if not apply:
        projected, changes = _preview(
            path,
            owner_policy,
            orphan_loan_policy,
            active_loan_policy,
        )
        return {
            "mode": "dry-run",
            "database": str(path),
            "backup": None,
            "policies": {
                "invalid_book_owner": owner_policy,
                "orphan_loan": orphan_loan_policy,
                "active_loan": active_loan_policy,
            },
            "before": before.to_dict(),
            "projected": projected.to_dict(),
            "changes": changes,
        }

    if before.invalid_owner_ids and owner_policy != OWNER_ARCHIVE_NULL:
        raise RepairPolicyError(
            "Invalid book owners exist; explicitly select --owner-policy archive-null"
        )
    if before.orphan_loans and orphan_loan_policy != LOAN_ARCHIVE_DELETE:
        raise RepairPolicyError(
            "Orphan loans exist; explicitly select --orphan-loan-policy archive-delete"
        )
    if (
        before.active_orphan_loans
        and orphan_loan_policy == LOAN_ARCHIVE_DELETE
        and not confirm_archive_active_loans
    ):
        raise RepairPolicyError(
            f"{before.active_orphan_loans} active orphan loan(s) would be archived; "
            "explicitly confirm --confirm-archive-active-loans"
        )

    destination_dir = (
        Path(backup_dir).resolve()
        if backup_dir
        else path.parent / "backups" / "migration"
    )
    backup_path = create_online_backup(path, destination_dir)

    try:
        connection = sqlite3.connect(path)
        try:
            after, changes = _run_repair_transaction(
                connection,
                owner_policy,
                orphan_loan_policy,
                active_loan_policy,
                commit=True,
                require_clean=True,
            )
        finally:
            connection.close()
    except Exception as exc:
        raise RepairValidationError(
            "Apply failed and was rolled back; pre-migration backup: "
            f"{backup_path}; error={type(exc).__name__}: {exc}"
        ) from exc

    return {
        "mode": "apply",
        "database": str(path),
        "backup": str(backup_path),
        "policies": {
            "invalid_book_owner": owner_policy,
            "orphan_loan": orphan_loan_policy,
            "active_loan": active_loan_policy,
            "archive_active_loans_confirmed": confirm_archive_active_loans,
        },
        "before": before.to_dict(),
        "after": after.to_dict(),
        "changes": changes,
    }


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Audit or repair known laBook foreign-key violations."
    )
    parser.add_argument("database", help="Path to the SQLite database")
    parser.add_argument(
        "--owner-policy",
        choices=(OWNER_REPORT, OWNER_ARCHIVE_NULL),
        default=OWNER_REPORT,
        help="How to handle invalid Books.owner_id values",
    )
    parser.add_argument(
        "--orphan-loan-policy",
        choices=(LOAN_REPORT, LOAN_ARCHIVE_DELETE),
        default=LOAN_REPORT,
        help="How to handle Loans rows whose book is missing",
    )
    parser.add_argument(
        "--active-loan-policy",
        choices=(ACTIVE_LOAN_REPORT, ACTIVE_LOAN_CREATE_INDEX),
        default=ACTIVE_LOAN_REPORT,
        help="Whether to create the one-active-loan-per-ISBN unique index",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the selected policies; otherwise use an in-memory dry-run",
    )
    parser.add_argument(
        "--confirm-services-stopped",
        action="store_true",
        help="Confirm all processes that write this database have been stopped",
    )
    parser.add_argument(
        "--confirm-archive-active-loans",
        action="store_true",
        help="Confirm that active orphan loans may be moved out of Loans",
    )
    parser.add_argument(
        "--backup-dir",
        help="Pre-migration backup directory (default: backups/migration beside DB)",
    )
    return parser


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.apply and not args.confirm_services_stopped:
        parser.error("--apply requires --confirm-services-stopped")

    try:
        report = repair_database(
            args.database,
            apply=args.apply,
            owner_policy=args.owner_policy,
            orphan_loan_policy=args.orphan_loan_policy,
            active_loan_policy=args.active_loan_policy,
            confirm_archive_active_loans=args.confirm_archive_active_loans,
            backup_dir=args.backup_dir,
        )
    except (FileNotFoundError, RepairPolicyError, RepairValidationError) as exc:
        parser.exit(1, f"repair_database: {exc}\n")

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
