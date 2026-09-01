import importlib
import unittest
from unittest import mock


class SecretConsumerImportTests(unittest.TestCase):
    def test_modules_do_not_read_secrets_during_import(self):
        with mock.patch(
            "config.get_setting",
            side_effect=AssertionError("secret read during module import"),
        ):
            for module_name in (
                "fetch_book_info",
                "routes.notion",
                "slack_notify",
            ):
                module = importlib.import_module(module_name)
                importlib.reload(module)


if __name__ == "__main__":
    unittest.main()
