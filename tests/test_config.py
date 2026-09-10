import os
import sys
import types
import unittest
import warnings
from unittest import mock

from config import MissingSettingError, get_setting


class GetSettingTests(unittest.TestCase):
    setting_name = "LABOOK_TEST_SETTING"

    def test_environment_has_priority_over_legacy_keys(self):
        legacy_keys = types.ModuleType("keys")
        legacy_keys.LABOOK_TEST_SETTING = "legacy-value"

        with mock.patch.dict(sys.modules, {"keys": legacy_keys}):
            with mock.patch.dict(
                os.environ, {self.setting_name: "environment-value"}, clear=False
            ):
                self.assertEqual(get_setting(self.setting_name), "environment-value")

    def test_legacy_keys_is_supported_during_migration(self):
        legacy_keys = types.ModuleType("keys")
        legacy_keys.LABOOK_TEST_SETTING = "legacy-value"

        with mock.patch.dict(sys.modules, {"keys": legacy_keys}):
            with mock.patch.dict(os.environ, {}, clear=True):
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    self.assertEqual(get_setting(self.setting_name), "legacy-value")

        self.assertEqual(len(caught), 1)
        self.assertIs(caught[0].category, DeprecationWarning)

    def test_missing_setting_error_contains_name_but_no_value(self):
        missing_keys = ModuleNotFoundError("No module named 'keys'", name="keys")

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("config.importlib.import_module", side_effect=missing_keys):
                with self.assertRaises(MissingSettingError) as caught:
                    get_setting(self.setting_name)

        self.assertIn(self.setting_name, str(caught.exception))

    def test_empty_environment_value_does_not_fall_back(self):
        legacy_keys = types.ModuleType("keys")
        legacy_keys.LABOOK_TEST_SETTING = "legacy-value"

        with mock.patch.dict(sys.modules, {"keys": legacy_keys}):
            with mock.patch.dict(os.environ, {self.setting_name: ""}, clear=False):
                with self.assertRaises(MissingSettingError):
                    get_setting(self.setting_name)


if __name__ == "__main__":
    unittest.main()
