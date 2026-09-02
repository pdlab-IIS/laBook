import unittest
from unittest import mock

import requests

from outbound_policy import (
    OutboundRequestBlocked,
    build_allowlisted_request,
    ensure_url_allowed,
    parse_allowed_hosts,
)


ALLOWED_HOSTS = {
    "ndlsearch.ndl.go.jp",
    "openapi.rakuten.co.jp",
    "www.googleapis.com",
}


class OutboundPolicyTests(unittest.TestCase):
    def test_parses_normalized_comma_separated_hosts(self):
        self.assertEqual(
            parse_allowed_hosts(" NDLSEARCH.NDL.GO.JP, www.googleapis.com, "),
            frozenset({"ndlsearch.ndl.go.jp", "www.googleapis.com"}),
        )

    def test_allows_only_https_on_the_configured_hosts(self):
        ensure_url_allowed(
            "https://ndlsearch.ndl.go.jp/api/opensearch?isbn=1",
            ALLOWED_HOSTS,
        )
        ensure_url_allowed(
            "https://www.googleapis.com:443/books/v1/volumes",
            ALLOWED_HOSTS,
        )

        blocked_urls = (
            "http://ndlsearch.ndl.go.jp/api/opensearch",
            "https://ndlsearch.ndl.go.jp:444/api/opensearch",
            "https://api.notion.com/v1/pages",
            "https://ndlsearch.ndl.go.jp.example.com/api/opensearch",
        )
        for url in blocked_urls:
            with self.subTest(url=url):
                with self.assertRaises(OutboundRequestBlocked):
                    ensure_url_allowed(url, ALLOWED_HOSTS)

    def test_wrapper_blocks_before_calling_requests(self):
        original_request = mock.Mock(return_value="response")
        wrapped_request = build_allowlisted_request(original_request, ALLOWED_HOSTS)
        session = requests.Session()

        self.assertEqual(
            wrapped_request(
                session,
                "GET",
                "https://openapi.rakuten.co.jp/services/api/test",
                timeout=5,
            ),
            "response",
        )
        original_request.assert_called_once()

        with self.assertRaises(OutboundRequestBlocked):
            wrapped_request(session, "POST", "https://api.notion.com/v1/pages")
        original_request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
