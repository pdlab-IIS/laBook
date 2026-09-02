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
        self.assertIn(
            b'<meta name="viewport" content="width=device-width, initial-scale=1">',
            response.data,
        )
        self.assertNotIn(b'developmentEnvironmentOverlay', response.data)
        self.assertNotIn(b'development_preview.js', response.data)

    def test_index_has_responsive_header_and_utility_menu(self):
        app.debug = False

        response = app.test_client().get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('<h1><i class="fa-solid fa-database"', html)
        self.assertIn('class="search-controls"', html)
        self.assertIn('id="utilityMenu"', html)
        self.assertIn('aria-label="メニュー"', html)
        self.assertIn('<span>リロード</span>', html)
        self.assertIn('<span>棚卸しモード</span>', html)
        self.assertIn('<span>アクセスモード</span>', html)

    def test_overlay_script_supports_pointer_dragging(self):
        with open("static/development_preview.js", encoding="utf-8") as source_file:
            source = source_file.read()

        self.assertIn("labook-development-preview-position-v1", source)
        self.assertIn("addEventListener('pointerdown'", source)
        self.assertIn("addEventListener('pointermove'", source)
        self.assertIn("setPointerCapture", source)
        self.assertIn("getPositionRange", source)


if __name__ == "__main__":
    unittest.main()
