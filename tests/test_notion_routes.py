import unittest
from unittest import mock

import requests
from flask import Flask

from http_config import EXTERNAL_API_TIMEOUT
from routes.notion import bp


class NotionRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(bp)
        self.client = self.app.test_client()

    @mock.patch("routes.notion.get_setting", return_value="dummy")
    @mock.patch("routes.notion.requests.post", side_effect=requests.Timeout())
    def test_add_timeout_returns_gateway_timeout(self, post, _get_setting):
        response = self.client.post(
            "/api/notion/add",
            json={
                "isbn": "9780000000001",
                "title": "Test",
                "reviewer": "Tester",
                "review": "Review",
            },
        )

        self.assertEqual(response.status_code, 504)
        self.assertEqual(post.call_args.kwargs["timeout"], EXTERNAL_API_TIMEOUT)


if __name__ == "__main__":
    unittest.main()
