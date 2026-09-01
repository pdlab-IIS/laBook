import sqlite3
import unittest
from unittest import mock

import app as app_module


class HealthRouteTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()

    def test_healthz_is_independent_of_database(self):
        with mock.patch("app.get_db", side_effect=AssertionError("database accessed")):
            response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_readyz_reports_available_database(self):
        database = sqlite3.connect(":memory:")
        self.addCleanup(database.close)

        with mock.patch("app.get_db", return_value=database):
            response = self.client.get("/readyz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"status": "ready", "database": "ok"},
        )

    def test_readyz_hides_database_error_details(self):
        database = mock.Mock()
        database.execute.side_effect = sqlite3.OperationalError(
            "sensitive database path"
        )

        with mock.patch("app.get_db", return_value=database):
            response = self.client.get("/readyz")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json(),
            {"status": "not_ready", "database": "unavailable"},
        )
        self.assertNotIn("sensitive", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
