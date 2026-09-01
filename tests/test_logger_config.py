import logging
import unittest

from logger_config import HANDLER_MARKER, setup_logger


class LoggerConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.root = logging.getLogger()
        self.original_handlers = list(self.root.handlers)
        self.original_level = self.root.level
        self.root.handlers = [
            handler
            for handler in self.root.handlers
            if not getattr(handler, HANDLER_MARKER, False)
        ]

    def tearDown(self):
        self.root.handlers = self.original_handlers
        self.root.setLevel(self.original_level)

    def test_setup_adds_only_one_stream_handler(self):
        first_logger = setup_logger("first")
        second_logger = setup_logger("second")
        handlers = [
            handler
            for handler in self.root.handlers
            if getattr(handler, HANDLER_MARKER, False)
        ]

        self.assertEqual(first_logger.name, "first")
        self.assertEqual(second_logger.name, "second")
        self.assertEqual(len(handlers), 1)
        self.assertIsInstance(handlers[0], logging.StreamHandler)
        self.assertFalse(hasattr(handlers[0], "baseFilename"))


if __name__ == "__main__":
    unittest.main()
