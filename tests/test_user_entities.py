import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from app import app
from db import initialize_database
from user_entities import migrate_user_entities
from scripts.smoke_test import run_smoke
from werkzeug.serving import make_server


class EntityRoutesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'library.db'
        initialize_database(self.path)
        self.database_patch = patch('db.DATABASE', str(self.path))
        self.database_patch.start()
        self.client = app.test_client()

    def tearDown(self):
        self.database_patch.stop()
        self.temp.cleanup()

    def user(self, name, **fields):
        response = self.client.post('/users', json={'user_name': name, **fields})
        self.assertEqual(response.status_code, 201)
        return response.json['user_id']

    def book(self, owner=None):
        response = self.client.post('/books', json={'isbn': 100, 'title': 'Book', 'owner_id': owner})
        self.assertEqual(response.status_code, 201)

    def test_new_people_are_not_owners_and_can_be_enabled(self):
        person = self.user('Person')
        data = self.client.get(f'/users/{person}').json
        self.assertEqual((data['entity_type'], data['can_own_books']), ('person', 0))
        self.assertEqual(self.client.post('/books', json={'isbn': 100, 'title': 'Book', 'owner_id': person}).status_code, 409)
        self.assertEqual(self.client.put(f'/users/{person}', json={'can_own_books': True}).status_code, 200)
        self.book(person)
        response = self.client.put(f'/users/{person}', json={'can_own_books': False})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.get(f'/users/{person}').json['name'], 'Person')
        self.assertEqual(self.client.put('/books/100', json={'title': 'Book', 'owner_id': ''}).status_code, 200)
        self.assertEqual(self.client.put(f'/users/{person}', json={'can_own_books': False}).status_code, 200)

    def test_organization_can_own_but_cannot_borrow_or_return(self):
        organization = self.user('Laboratory', entity_type='organization', can_own_books=True)
        person = self.user('Person')
        self.book(organization)
        self.assertEqual(self.client.get('/users/by_name/Laboratory').status_code, 409)
        self.assertEqual(self.client.post('/loans', json={'isbn': 100, 'borrower_id': organization}).status_code, 409)
        loan = self.client.post('/loans', json={'isbn': 100, 'borrower_id': person})
        self.assertEqual(loan.status_code, 201)
        loan_id = loan.json['loan_id']
        self.assertEqual(self.client.post(f'/loans/{loan_id}', json={'returner_id': organization}).status_code, 409)
        self.assertIsNone(self.client.get(f'/loans/{loan_id}').json['return_date'])
        self.assertEqual(self.client.post(f'/loans/{loan_id}', json={'returner_id': person}).status_code, 200)
        self.assertEqual(self.client.put(f'/users/{person}', json={'entity_type': 'organization'}).status_code, 409)

    def test_person_lookup_prefers_person_with_shared_name(self):
        self.user('Shared', entity_type='organization')
        person = self.user('Shared')
        self.assertEqual(self.client.get('/users/by_name/Shared').json['user_id'], person)

    def test_invalid_entity_settings_are_rejected(self):
        for values in ({'entity_type': 'robot'}, {'can_own_books': 'false'}, {'can_own_books': 2}, {'user_name': ' '}):
            with self.subTest(values=values):
                self.assertEqual(self.client.post('/users', json={'user_name': 'Name', **values}).status_code, 400)

    def test_book_manage_only_selects_owner_and_settings_have_own_page(self):
        excluded = self.user('Not eligible')
        eligible = self.user('<Lab>', entity_type='organization', can_own_books=True)
        html = self.client.get('/books/manage').get_data(as_text=True)
        selector = html.split('<select name="owner_id" id="owner_id">')[1].split('</select>')[0]
        self.assertNotIn(f'value="{excluded}"', selector)
        self.assertIn(f'value="{eligible}"', selector)
        self.assertIn('&lt;Lab&gt;', selector)
        self.assertNotIn('id="ownerSettingsForm"', html)
        self.assertNotIn('owner_settings.js', html)
        settings = self.client.get('/users/manage')
        self.assertEqual(settings.status_code, 200)
        self.assertIn('id="ownerSettingsForm"', settings.get_data(as_text=True))
        self.assertIn('Not eligible', settings.get_data(as_text=True))
        self.assertIn('&lt;Lab&gt;', settings.get_data(as_text=True))
        self.assertNotIn('<Lab>', settings.get_data(as_text=True))
        self.assertNotIn('id="ownerSettingsForm"', self.client.get('/').get_data(as_text=True))
        home = self.client.get('/').get_data(as_text=True)
        self.assertIn('id="manageUsersBtn"', home)
        self.assertIn('data-url="/users/manage"', home)

    def test_users_page_empty_states(self):
        html = self.client.get('/users/manage').get_data(as_text=True)
        self.assertIn('人物・組織はまだ登録されていません。', html)
        self.assertIn('貸出中の本はありません。', html)

    def test_delete_unused_entity_but_preserve_owners_and_loan_history(self):
        unused = self.user('Unused', entity_type='organization')
        self.assertEqual(self.client.delete(f'/users/{unused}').status_code, 200)
        owner = self.user('Owner', can_own_books=True)
        person = self.user('Borrower')
        self.book(owner)
        loan = self.client.post('/loans', json={'isbn': 100, 'borrower_id': person}).json['loan_id']
        self.assertEqual(self.client.delete(f'/users/{owner}').status_code, 409)
        self.assertEqual(self.client.delete(f'/users/{person}').status_code, 409)
        self.assertEqual(self.client.post(f'/loans/{loan}', json={'returner_id': person}).status_code, 200)
        self.assertEqual(self.client.delete(f'/users/{person}').status_code, 409)
        html = self.client.get('/users/manage').get_data(as_text=True)
        self.assertIn('disabled title="所有する本または貸出・返却履歴があります"', html)

    def test_loan_list_defaults_active_and_paginates_all_history(self):
        borrower = self.user('<Borrower>')
        self.book()
        with closing(sqlite3.connect(self.path)) as db:
            for index in range(26):
                db.execute('''INSERT INTO Loans (isbn, borrower_id, returner_id, loan_date, due_date, return_date)
                    VALUES (100, ?, ?, '2026-09-01', '2026-09-07', '2026-09-02')''', (borrower, borrower))
            db.commit()
        self.assertEqual(self.client.post('/loans', json={'isbn': 100, 'borrower_id': borrower}).status_code, 201)
        active = self.client.get('/users/manage').get_data(as_text=True)
        self.assertIn('1件 / 1 / 1ページ', active)
        self.assertIn('&lt;Borrower&gt;', active)
        self.assertNotIn('<Borrower>', active)
        first = self.client.get('/users/manage?view=all').get_data(as_text=True)
        self.assertIn('27件 / 1 / 2ページ', first)
        self.assertEqual(first.count('data-label="本"'), 25)
        second = self.client.get('/users/manage?view=all&page=2').get_data(as_text=True)
        self.assertEqual(second.count('data-label="本"'), 2)
        self.assertNotIn('data-label="返却期限"', second)
        self.assertNotIn('data-label="状態"', second)
        self.assertIn('href="/books/manage?isbn=100"', second)
        clamped = self.client.get('/users/manage?view=all&page=999').get_data(as_text=True)
        self.assertIn('27件 / 2 / 2ページ', clamped)

    def test_database_guards_direct_writes(self):
        person = self.user('Person', can_own_books=True)
        organization = self.user('Lab', entity_type='organization')
        self.book(person)
        with closing(sqlite3.connect(self.path)) as db:
            for sql, args in (
                ('UPDATE Users SET can_own_books=0 WHERE user_id=?', (person,)),
                ('UPDATE Books SET owner_id=? WHERE isbn=100', (organization,)),
                ('INSERT INTO Loans (isbn, borrower_id, loan_date) VALUES (100, ?, CURRENT_TIMESTAMP)', (organization,)),
            ):
                with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                    db.execute(sql, args)

    def test_existing_http_smoke_workflow_on_new_schema(self):
        server = make_server('127.0.0.1', 0, app)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            self.assertEqual(run_smoke(f'http://127.0.0.1:{server.server_port}'), 30)
        finally:
            server.shutdown()
            worker.join(timeout=5)
            server.server_close()


class EntityMigrationTests(unittest.TestCase):
    def legacy_db(self):
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.executescript('''
            CREATE TABLE Users (user_id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE Books (isbn INTEGER PRIMARY KEY, owner_id INTEGER);
            CREATE TABLE Loans (borrower_id INTEGER, returner_id INTEGER);
            INSERT INTO Users VALUES (1, 'Owner'), (2, 'Borrower');
            INSERT INTO Books VALUES (100, 1);
        ''')
        return db

    def test_migration_preserves_owners_and_is_idempotent(self):
        db = self.legacy_db()
        migrate_user_entities(db)
        self.assertEqual(db.execute('SELECT entity_type, can_own_books FROM Users ORDER BY user_id').fetchall(), [('person', 1), ('person', 0)])
        self.assertEqual(db.execute('SELECT owner_id FROM Books').fetchone()[0], 1)
        db.execute('UPDATE Users SET can_own_books=1 WHERE user_id=2')
        db.commit()
        migrate_user_entities(db)
        self.assertEqual(db.execute('SELECT can_own_books FROM Users WHERE user_id=2').fetchone()[0], 1)

    def test_invalid_legacy_owner_rolls_back_schema_changes(self):
        db = self.legacy_db()
        db.execute('UPDATE Books SET owner_id=404')
        db.commit()
        with self.assertRaises(ValueError):
            migrate_user_entities(db)
        self.assertNotIn('entity_type', [r[1] for r in db.execute('PRAGMA table_info(Users)')])
