import sqlite3
import unittest
from html.parser import HTMLParser
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from app import app


class LocationNavigationTests(unittest.TestCase):
    def test_pagination_controls_surround_table_without_duplicate_ids(self):
        html = app.test_client().get("/").get_data(as_text=True)
        self.assertLess(html.index('id="paginationTop"'), html.index('id="booksTable"'))
        self.assertLess(html.index('id="booksTable"'), html.index('id="pagination"'))
        self.assertEqual(html.count('data-page-action="prev"'), 2)
        self.assertEqual(html.count('data-page-action="next"'), 2)

        class IdCollector(HTMLParser):
            ids = None

            def handle_starttag(self, tag, attrs):
                self.ids.extend(value for key, value in attrs if key == "id")

        parser = IdCollector()
        parser.ids = []
        parser.feed(html)
        self.assertEqual(len(parser.ids), len(set(parser.ids)))

    def test_location_link_and_legacy_id_show_location_name(self):
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE TABLE Shelves (shelf_id INTEGER, shelf_code TEXT)")
            db.execute("INSERT INTO Shelves VALUES (7, 'A & B')")
            client = app.test_client()
            with mock.patch("app.get_db", return_value=db):
                response = client.get("/L/A%20%26%20B")
                self.assertEqual(response.status_code, 302)
                query = parse_qs(urlsplit(response.location).query)
                self.assertEqual(query, {"location": ["A & B"]})
                named = client.get(response.location).get_data(as_text=True)
                legacy = client.get("/?shelf_id=7").get_data(as_text=True)
            for html in (named, legacy):
                self.assertIn('window.initialShelfFilter = "A \\u0026 B";', html)
                self.assertNotIn('window.initialShelfFilter = "shelf_id:', html)


if __name__ == "__main__":
    unittest.main()
