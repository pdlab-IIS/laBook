import unittest

import app as app_module


class AdminRouteExposureTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True, DEBUG=True)
        self.client = app_module.app.test_client()

    def test_backup_is_not_exposed_over_http(self):
        self.assertEqual(self.client.get("/backup").status_code, 404)

    def test_initdb_is_not_exposed_even_in_debug_mode(self):
        self.assertEqual(self.client.get("/initdb").status_code, 404)


if __name__ == "__main__":
    unittest.main()
