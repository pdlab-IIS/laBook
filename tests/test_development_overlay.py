import unittest

from app import app


class DevelopmentOverlayTests(unittest.TestCase):
    def setUp(self):
        self.original_debug = app.debug
        self.original_testing = app.testing
        app.testing = True

    def tearDown(self):
        app.debug = self.original_debug
        app.testing = self.original_testing

    def test_overlay_is_present_in_debug_mode(self):
        app.debug = True

        response = app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'developmentEnvironmentOverlay', response.data)
        self.assertIn(b'development_preview.js', response.data)
        self.assertIn(b'data-development-preview-mode="sp700"', response.data)
        self.assertIn(b'data-development-preview-mode="pc"', response.data)
        self.assertIn(b'data-development-preview-mode="device"', response.data)

    def test_overlay_is_absent_outside_debug_mode(self):
        app.debug = False

        response = app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'developmentEnvironmentOverlay', response.data)
        self.assertNotIn(b'development_preview.js', response.data)


if __name__ == "__main__":
    unittest.main()
