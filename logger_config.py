import logging
from logging.handlers import RotatingFileHandler
import os

def _handler_for_filename_exists(filename):
    if not filename:
        return False
    abspath = os.path.abspath(filename)
    for h in logging.getLogger().handlers:
        base = getattr(h, "baseFilename", None)
        if base and os.path.abspath(base) == abspath:
            return True
    return False

def setup_logger(name="labook", log_file="labook.log"):
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not _handler_for_filename_exists(log_file):
        handler = RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=500, encoding="utf-8"
        )
        handler.setLevel(logging.INFO)
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(levelname)s in %(module)s: %(message)s")
        )
        root.addHandler(handler)
        root.addHandler(logging.StreamHandler())
    return logging.getLogger(name)