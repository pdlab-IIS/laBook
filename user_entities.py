"""Transactional migration and database invariants for people/organizations."""

TRIGGERS = (
    """CREATE TRIGGER IF NOT EXISTS eligible_book_owner_insert
    BEFORE INSERT ON Books WHEN NEW.owner_id IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM Users WHERE user_id=NEW.owner_id AND can_own_books=1)
    BEGIN SELECT RAISE(ABORT, 'Owner is not eligible'); END""",
    """CREATE TRIGGER IF NOT EXISTS eligible_book_owner_update
    BEFORE UPDATE OF owner_id ON Books WHEN NEW.owner_id IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM Users WHERE user_id=NEW.owner_id AND can_own_books=1)
    BEGIN SELECT RAISE(ABORT, 'Owner is not eligible'); END""",
    """CREATE TRIGGER IF NOT EXISTS retain_owner_eligibility
    BEFORE UPDATE OF can_own_books ON Users WHEN NEW.can_own_books=0
    AND EXISTS (SELECT 1 FROM Books WHERE owner_id=OLD.user_id)
    BEGIN SELECT RAISE(ABORT, 'Reassign owned books first'); END""",
    """CREATE TRIGGER IF NOT EXISTS retain_person_loan_history
    BEFORE UPDATE OF entity_type ON Users WHEN NEW.entity_type='organization'
    AND EXISTS (SELECT 1 FROM Loans WHERE borrower_id=OLD.user_id OR returner_id=OLD.user_id)
    BEGIN SELECT RAISE(ABORT, 'Loan participants must remain people'); END""",
    """CREATE TRIGGER IF NOT EXISTS person_loan_insert
    BEFORE INSERT ON Loans WHEN
    NOT EXISTS (SELECT 1 FROM Users WHERE user_id=NEW.borrower_id AND entity_type='person')
    OR (NEW.returner_id IS NOT NULL AND NOT EXISTS
        (SELECT 1 FROM Users WHERE user_id=NEW.returner_id AND entity_type='person'))
    BEGIN SELECT RAISE(ABORT, 'Loan participants must be people'); END""",
    """CREATE TRIGGER IF NOT EXISTS person_loan_update
    BEFORE UPDATE OF borrower_id, returner_id ON Loans WHEN
    NOT EXISTS (SELECT 1 FROM Users WHERE user_id=NEW.borrower_id AND entity_type='person')
    OR (NEW.returner_id IS NOT NULL AND NOT EXISTS
        (SELECT 1 FROM Users WHERE user_id=NEW.returner_id AND entity_type='person'))
    BEGIN SELECT RAISE(ABORT, 'Loan participants must be people'); END""",
)


def migrate_user_entities(connection):
    """Preserve existing owners, default everyone else to ineligible people."""
    try:
        connection.execute("BEGIN IMMEDIATE")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(Users)")}
        if "entity_type" not in columns:
            connection.execute("ALTER TABLE Users ADD COLUMN entity_type TEXT NOT NULL DEFAULT 'person' CHECK(entity_type IN ('person', 'organization'))")
        if "can_own_books" not in columns:
            connection.execute("ALTER TABLE Users ADD COLUMN can_own_books INTEGER NOT NULL DEFAULT 0 CHECK(can_own_books IN (0, 1))")
            connection.execute("UPDATE Users SET can_own_books=1 WHERE user_id IN (SELECT owner_id FROM Books WHERE owner_id IS NOT NULL)")
        if connection.execute("""SELECT 1 FROM Books b WHERE b.owner_id IS NOT NULL
            AND NOT EXISTS (SELECT 1 FROM Users u WHERE u.user_id=b.owner_id AND u.can_own_books=1) LIMIT 1""").fetchone():
            raise ValueError("Resolve invalid book owners before migration")
        if connection.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("Resolve foreign key violations before migration")
        for statement in TRIGGERS:
            connection.execute(statement)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
