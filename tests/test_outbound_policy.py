import unittest
from unittest import mock
from pathlib import Path

import requests

from outbound_policy import (
    OutboundRequestBlocked,
    build_allowlisted_request,
    ensure_url_allowed,
    parse_allowed_hosts,
)


ALLOWED_HOSTS = {
    "books.google.com",
    "ndlsearch.ndl.go.jp",
    "openapi.rakuten.co.jp",
    "thumbnail.image.rakuten.co.jp",
    "www.googleapis.com",
}


class OutboundPolicyTests(unittest.TestCase):
    def test_development_and_systemd_allowlists_match_policy_hosts(self):
        env_lines = Path(".env.example").read_text(encoding="utf-8").splitlines()
        env_value = next(
            line.split("=", 1)[1]
            for line in env_lines
            if line.startswith("LABOOK_OUTBOUND_ALLOWLIST=")
        )
        self.assertEqual(parse_allowed_hosts(env_value), frozenset(ALLOWED_HOSTS))

        service_text = Path("deploy/systemd/labook.service").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            f"Environment=LABOOK_OUTBOUND_ALLOWLIST={env_value}",
            service_text,
        )

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
        ensure_url_allowed(
            "https://thumbnail.image.rakuten.co.jp/@0_mall/book/cabinet/cover.jpg",
            ALLOWED_HOSTS,
        )
        ensure_url_allowed(
            "https://books.google.com/books?id=test&printsec=frontcover&img=1",
            ALLOWED_HOSTS,
        )

        blocked_urls = (
            "http://ndlsearch.ndl.go.jp/api/opensearch",
            "http://books.google.com/books?id=test&img=1",
            "https://ndlsearch.ndl.go.jp:444/api/opensearch",
            "https://api.notion.com/v1/pages",
            "https://ndlsearch.ndl.go.jp.example.com/api/opensearch",
            "https://thumbnail.image.rakuten.co.jp.example.com/cover.jpg",
            "https://books.google.com.example.com/cover.jpg",
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
