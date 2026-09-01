import unittest
from unittest import mock

import requests

import fetch_book_info
from http_config import EXTERNAL_API_TIMEOUT


class PublicationDateTests(unittest.TestCase):
    def test_normalizes_supported_date_precisions(self):
        cases = {
            "2026": "2026-01-01",
            "2026-09": "2026-09-01",
            "2026-09-01": "2026-09-01",
        }

        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(
                    fetch_book_info.normalize_publication_date(value), expected
                )

    def test_rejects_invalid_or_missing_date(self):
        for value in (None, "", "2026-13", "not-a-date"):
            with self.subTest(value=value):
                self.assertIsNone(fetch_book_info.normalize_publication_date(value))


class ProviderTests(unittest.TestCase):
    @mock.patch("fetch_book_info.get_setting", return_value="dummy-key")
    @mock.patch("fetch_book_info.requests.get")
    def test_google_request_has_timeout(self, get, _get_setting):
        response = mock.Mock()
        response.json.return_value = {"items": []}
        get.return_value = response

        self.assertIsNone(fetch_book_info.get_google_book_info("9780000000001"))

        response.raise_for_status.assert_called_once_with()
        self.assertEqual(get.call_args.kwargs["timeout"], EXTERNAL_API_TIMEOUT)
        self.assertEqual(get.call_args.kwargs["params"]["key"], "dummy-key")

    @mock.patch("fetch_book_info.save_cover_image", return_value=None)
    @mock.patch("fetch_book_info.get_ndl_book_info", return_value=None)
    @mock.patch(
        "fetch_book_info.get_rakuten_book_info",
        return_value={
            "title": "Fallback title",
            "author": None,
            "publisher": None,
            "date": "2026-09-01",
            "cover_url": None,
        },
    )
    @mock.patch(
        "fetch_book_info.get_google_book_info",
        side_effect=requests.Timeout("provider timeout"),
    )
    def test_one_provider_failure_keeps_partial_result(
        self,
        _google,
        _rakuten,
        _ndl,
        _save_cover,
    ):
        result = fetch_book_info.fetch_book_info("9780000000001")

        self.assertEqual(result["title"], "Fallback title")
        self.assertEqual(result["publication_date"], "2026-09-01")


if __name__ == "__main__":
    unittest.main()
