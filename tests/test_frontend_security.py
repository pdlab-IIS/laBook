import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendSecurityTests(unittest.TestCase):
    def test_external_book_and_review_data_is_not_inserted_as_html(self):
        index_source = (ROOT / "static" / "index.js").read_text(encoding="utf-8")
        form_source = (ROOT / "static" / "book_form.js").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("tr.innerHTML", index_source)
        self.assertNotIn("spnLockMode.innerHTML", index_source)
        self.assertNotIn("tr.innerHTML", form_source)
        self.assertNotIn("Error: ${e}", form_source)
        self.assertIn("reviewCell.textContent = review", form_source)
        self.assertIn("title.textContent = book.title", index_source)

    def test_borrowed_filter_is_requested_from_the_full_dataset(self):
        index_source = (ROOT / "static" / "index.js").read_text(encoding="utf-8")

        self.assertIn("url += '&status=borrowed'", index_source)
        self.assertNotIn("limit=99999", index_source)


if __name__ == "__main__":
    unittest.main()
