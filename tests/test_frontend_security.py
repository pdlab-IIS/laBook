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
        self.assertNotIn("spnSpd.innerHTML", index_source)
        self.assertIn("spnSpd.replaceChildren", index_source)
        self.assertIn("inventoryLocationText.textContent", index_source)
        self.assertNotIn("inventoryLocationText.innerHTML", index_source)
        self.assertIn("inventoryIsbnMessage.textContent", index_source)
        self.assertNotIn("inventoryIsbnMessage.innerHTML", index_source)
        self.assertIn("function validateInventoryIsbnInput()", index_source)
        self.assertIn("if (!isbnValidate(normalizedIsbn))", index_source)
        self.assertIn("'invalid / 無効:", index_source)
        self.assertIn("`success / 成功:", index_source)
        self.assertIn("'unknown / 書誌情報なし:", index_source)
        self.assertIn("function setInventoryProcessing(active, isbn = '')", index_source)
        self.assertIn("function rememberShelf(result, fallbackLocation)", index_source)
        self.assertIn("shelfCache[shelfId] = shelfCode", index_source)
        self.assertIn("await processInventoryIsbn(normalizedIsbn)", index_source)
        self.assertIn("loadingIndicator.hidden = false", index_source)
        self.assertIn("booksTable.setAttribute('aria-busy', 'true')", index_source)
        self.assertIn("booksTable.removeAttribute('aria-busy')", index_source)
        self.assertNotIn("tr.innerHTML", form_source)
        self.assertNotIn("Error: ${e}", form_source)
        self.assertIn("reviewCell.textContent = review", form_source)
        self.assertIn("title.textContent = book.title", index_source)
        self.assertIn("compactMeta.textContent", index_source)
        self.assertNotIn("compactMeta.innerHTML", index_source)
        self.assertIn("compactAuthor.textContent", index_source)
        self.assertNotIn("compactAuthor.innerHTML", index_source)

    def test_borrowed_filter_is_requested_from_the_full_dataset(self):
        index_source = (ROOT / "static" / "index.js").read_text(encoding="utf-8")

        self.assertIn("url += '&status=borrowed'", index_source)
        self.assertNotIn("limit=99999", index_source)

    def test_responsive_breakpoint_avoids_legacy_oversized_controls(self):
        style_source = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
        tablet_rules = style_source.split("@media (max-width: 1000px)", 1)[1].split(
            "@media (max-width: 700px)", 1
        )[0]

        self.assertIn("@container app-page (max-width: 760px)", style_source)
        self.assertNotIn("font-size: 2.5rem", tablet_rules)
        self.assertIn("width: auto;", tablet_rules)
        self.assertIn("font-size: 1rem;", tablet_rules)


if __name__ == "__main__":
    unittest.main()
