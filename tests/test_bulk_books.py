import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from app import app
from db import initialize_database


class BulkBookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'library.db'
        initialize_database(self.path)
        self.patch = patch('db.DATABASE', str(self.path))
        self.patch.start()
        self.client = app.test_client()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("INSERT INTO Users (user_id,name,can_own_books) VALUES (1,'Owner',1),(2,'Reader',0)")
            db.execute("INSERT INTO Shelves (shelf_id,shelf_code) VALUES (1,'Original')")
            db.executemany("INSERT INTO Books (isbn,title,shelf_id) VALUES (?, 'Keep title', 1)", [(100,), (200,), (300,)])
            db.commit()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def rows(self):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute('SELECT isbn,title,shelf_id,owner_id FROM Books ORDER BY isbn').fetchall()

    def test_only_selected_books_and_specified_fields_change(self):
        response = self.client.patch('/books/bulk', json={'isbns': ['100', '200'], 'location': ' New ', 'owner_id': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'updated_count': 2})
        first, second, untouched = self.rows()
        self.assertEqual(first[1:], ('Keep title', 2, 1))
        self.assertEqual(second[1:], first[1:])
        self.assertEqual(untouched, (300, 'Keep title', 1, None))
        response = self.client.patch('/books/bulk', json={'isbns': [100], 'owner_id': None})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.rows()[0], (100, 'Keep title', 2, None))
        self.assertEqual(self.client.patch('/books/bulk', json={'isbns': [200], 'location': None}).status_code, 200)
        self.assertEqual(self.rows()[1], (200, 'Keep title', None, 1))

    def test_duplicates_are_counted_once_and_existing_location_is_reused(self):
        response = self.client.patch('/books/bulk', json={'isbns': [100, '100'], 'location': 'Original'})
        self.assertEqual(response.json, {'updated_count': 1})
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM Shelves').fetchone()[0], 1)

    def test_invalid_targets_and_owners_do_not_change_anything(self):
        before = self.rows()
        for payload in (
            {'isbns': [100, 404], 'location': 'Do not create'},
            {'isbns': [100], 'location': 'Do not create', 'owner_id': 2},
            {'isbns': [100], 'owner_id': 404},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.patch('/books/bulk', json=payload).status_code, 409)
                self.assertEqual(self.rows(), before)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM Shelves').fetchone()[0], 1)

    def test_mid_update_failure_rolls_back_books_and_new_location(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("CREATE TRIGGER reject_second BEFORE UPDATE ON Books WHEN NEW.isbn=200 BEGIN SELECT RAISE(ABORT,'Test failure'); END")
            db.commit()
        before = self.rows()
        response = self.client.patch('/books/bulk', json={'isbns': [100, 200], 'location': 'Rollback', 'owner_id': 1})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.rows(), before)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM Shelves').fetchone()[0], 1)

    def test_invalid_payloads_are_rejected(self):
        for payload in ([], {}, {'isbns': []}, {'isbns': [100]},
                        {'isbns': [100], 'title': 'Not allowed'},
                        {'isbns': [True], 'location': None},
                        {'isbns': ['x'], 'location': None},
                        {'isbns': [2**63], 'location': None},
                        {'isbns': [100] * 101, 'location': None},
                        {'isbns': [100], 'location': ''},
                        {'isbns': [100], 'location': 3}):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.patch('/books/bulk', json=payload).status_code, 400)

    def test_index_has_selection_column_and_bulk_dialog(self):
        html = self.client.get('/').get_data(as_text=True)
        self.assertIn('id="selectPageBooks"', html)
        self.assertIn('aria-label="表示中のページを全選択"', html)
        self.assertLess(html.index('id="selectPageBooks"'), html.index('<th class="book-cover-column">Cover</th>'))
        self.assertIn('id="bulkEditBtn"', html)
        self.assertIn('<dialog id="bulkEditDialog"', html)
        self.assertIn('変更しない', html)
        self.assertIn('未設定にする', html)

    def test_bulk_mode_starts_without_selection_and_keeps_page_interactive(self):
        html = self.client.get('/').get_data(as_text=True)
        self.assertIn('<th class="book-selection" hidden>', html)
        self.assertIn('id="bulkEditBtn" class="utility-menu__item grey" aria-pressed="false"', html)
        self.assertIn('一括編集を終了', html)
        source = (Path(__file__).resolve().parents[1] / 'static/bulk_edit.js').read_text(encoding='utf-8')
        self.assertIn('dialog.show();', source)
        self.assertNotIn('showModal', source)
        submit = source.split("form.addEventListener('submit'", 1)[1]
        self.assertIn('dialog.close()', submit)
        self.assertLess(submit.index('if (!window.confirm('), submit.index('busy = true'))
        self.assertLess(submit.index('if (!response.ok)'), submit.index('dialog.close()'))
        self.assertLess(submit.index('dialog.close()'), submit.index('await loadAllShelves()'))
        self.assertIn('Location: ${locationSummary}', submit)
        self.assertIn('Owner: ${ownerSummary}', submit)
        self.assertIn('${payload.isbns.length}冊', submit)
        close_handler = source.split("dialog.addEventListener('close'", 1)[1].split("form.addEventListener", 1)[0]
        self.assertIn('active = false', close_handler)
        self.assertIn('box.checked = false', close_handler)
        self.assertIn('isbns: [...selection]', submit)
        self.assertIn('cell.hidden = !active', source)

    def test_owner_ids_are_not_visible_option_labels(self):
        import re
        for path in ('/books/manage', '/users/manage'):
            html = self.client.get(path).get_data(as_text=True)
            labels = re.findall(r'<option\b[^>]*>(.*?)</option>', html, re.S)
            self.assertTrue(labels)
            self.assertTrue(all('ID:' not in label for label in labels))
        source = (Path(__file__).resolve().parents[1] / 'static/bulk_edit.js').read_text(encoding='utf-8')
        self.assertIn('new Option(user.name, String(user.user_id))', source)
        self.assertNotIn('(ID:', source)

    def test_bulk_edit_is_desktop_only_without_menu_counter(self):
        root = Path(__file__).resolve().parents[1]
        html = self.client.get('/').get_data(as_text=True)
        self.assertIn('<span>Bulk Edit</span>', html)
        self.assertNotIn('bulkSelectedCount', html)
        source = (root / 'static/bulk_edit.js').read_text(encoding='utf-8')
        self.assertNotIn('bulkSelectedCount', source)
        self.assertIn('new ResizeObserver', source)
        self.assertIn('if (!desktopAvailable() && active)', source)
        self.assertIn('if (!desktopAvailable() || busy) return;', source)
        styles = (root / 'static/style.css').read_text(encoding='utf-8')
        self.assertIn('#bulkEditBtn { --bulk-available: 0; display: none; }', styles)
        self.assertIn('#booksTable th.book-title-column { width: auto; }', styles)
        self.assertIn('width: clamp(56px, 9cqi, 62px);', styles)
        self.assertIn('width: clamp(62px, 14cqi, 90px);', styles)
        self.assertNotIn('#booksTable th:nth-child', styles)
