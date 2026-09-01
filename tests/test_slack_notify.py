import unittest
from unittest import mock

import requests

import slack_notify
from http_config import EXTERNAL_API_TIMEOUT


class SlackNotifyTests(unittest.TestCase):
    @mock.patch("slack_notify.get_setting", return_value="dummy")
    @mock.patch("slack_notify.requests.post")
    def test_notion_query_has_timeout(self, post, _get_setting):
        response = mock.Mock(status_code=200)
        response.json.return_value = {"results": []}
        post.return_value = response

        slack_notify.send_new_notion_entries_to_slack()

        self.assertEqual(post.call_args.kwargs["timeout"], EXTERNAL_API_TIMEOUT)

    @mock.patch("slack_notify.get_setting", return_value="dummy")
    @mock.patch(
        "slack_notify.requests.post",
        side_effect=requests.Timeout("upstream timeout"),
    )
    def test_request_timeout_does_not_escape_background_job(self, _post, _get_setting):
        slack_notify.send_new_notion_entries_to_slack()


if __name__ == "__main__":
    unittest.main()
