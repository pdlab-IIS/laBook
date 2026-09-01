import unittest
from unittest import mock

import subapp


class SubappTests(unittest.TestCase):
    def test_main_runs_slack_scheduler_in_foreground(self):
        with mock.patch("slack_notify.loop") as loop:
            subapp.main()

        loop.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
