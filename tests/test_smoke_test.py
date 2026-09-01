import argparse
import unittest

from scripts.smoke_test import validate_target


class SmokeTargetSafetyTests(unittest.TestCase):
    def setUp(self):
        self.parser = argparse.ArgumentParser()

    def test_requires_disposable_database_confirmation(self):
        with self.assertRaises(SystemExit):
            validate_target(self.parser, "http://127.0.0.1:5100", False)

    def test_rejects_non_loopback_target(self):
        with self.assertRaises(SystemExit):
            validate_target(self.parser, "http://100.65.97.87:5100", True)

    def test_rejects_production_port(self):
        with self.assertRaises(SystemExit):
            validate_target(self.parser, "http://127.0.0.1:5000", True)

    def test_accepts_explicit_alternate_loopback_port(self):
        validate_target(self.parser, "http://127.0.0.1:5100", True)


if __name__ == "__main__":
    unittest.main()
