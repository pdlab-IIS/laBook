"""Regression checks for the shared list/manage page width contract."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PageLayoutTests(unittest.TestCase):
    def setUp(self):
        self.styles = (ROOT / "static/style.css").read_text(encoding="utf-8")

    def declarations(self, selector):
        match = re.search(re.escape(selector) + r"\s*\{([^}]+)\}", self.styles)
        self.assertIsNotNone(match)
        return dict(
            declaration.strip().split(":", 1)
            for declaration in match.group(1).split(";")
            if declaration.strip()
        )

    def test_list_and_manage_share_a_fluid_centered_1000px_page(self):
        for template, classes in (
            ("index.html", "app-page book-list-page"),
            ("manage_book.html", "app-page manage-page"),
        ):
            html = (ROOT / "templates" / template).read_text(encoding="utf-8")
            self.assertIn(f'<body class="{classes}">', html)

        rules = self.declarations("body.app-page")
        self.assertEqual(rules["width"].strip(), "100%")
        self.assertEqual(rules["max-width"].strip(), "1000px")
        self.assertEqual(rules["margin"].strip(), "0 auto")
        self.assertEqual(rules["padding"].strip(), "clamp(20px, 3vw, 40px)")

    def test_fixed_pc_preview_uses_the_same_desktop_width(self):
        rules = self.declarations('html[data-development-preview-mode="pc"] body')
        for property_name in ("width", "min-width", "max-width"):
            self.assertEqual(rules[property_name].strip(), "1000px")

    def test_manage_controls_include_padding_in_the_shared_right_edge(self):
        rules = self.declarations(".manage-page :is(input, textarea, select)")
        for name, value in {
            "display": "block",
            "box-sizing": "border-box",
            "width": "100%",
            "min-width": "0",
            "max-width": "100%",
            "inline-size": "100%",
            "min-inline-size": "0",
            "max-inline-size": "100%",
            "margin": "0",
        }.items():
            self.assertEqual(rules[name].strip(), value)

    def test_publication_keeps_date_semantics_without_native_minimum_width(self):
        html = (ROOT / "templates/manage_book.html").read_text(encoding="utf-8")
        self.assertIn('type="date" name="publication_date"', html)
        rules = self.declarations('.manage-page input[type="date"]')
        self.assertEqual(rules["appearance"].strip(), "none")
        self.assertEqual(rules["-webkit-appearance"].strip(), "none")
        for pseudo in ("::-webkit-date-and-time-value", "::-webkit-datetime-edit"):
            rules = self.declarations('.manage-page input[type="date"]' + pseudo)
            self.assertEqual(rules["min-width"].strip(), "0")

    def test_loan_table_uses_the_standard_compact_table_layout(self):
        rules = self.declarations(".people-page .loans-table")
        self.assertEqual(rules["width"].strip(), "100%")
        self.assertEqual(rules["table-layout"].strip(), "fixed")


if __name__ == "__main__":
    unittest.main()
