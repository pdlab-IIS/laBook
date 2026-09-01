import logging

HANDLER_MARKER = "_labook_console_handler"


def setup_logger(name="labook"):
    """Configure one process-safe stderr handler for journald capture."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(getattr(handler, HANDLER_MARKER, False) for handler in root.handlers):
        handler = logging.StreamHandler()
        setattr(handler, HANDLER_MARKER, True)
        handler.setLevel(logging.INFO)
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(levelname)s in %(module)s: %(message)s")
        )
        root.addHandler(handler)
    return logging.getLogger(name)
