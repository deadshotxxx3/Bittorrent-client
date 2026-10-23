import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER = "bitclient"


def setup_logging(path) -> logging.Logger:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(path, maxBytes=512 * 1024, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)

    def on_exception(kind, value, trace):
        logger.error("Unhandled exception", exc_info=(kind, value, trace))
        sys.__excepthook__(kind, value, trace)

    def on_thread_exception(args):
        logger.error("Thread exception", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = on_exception
    threading.excepthook = on_thread_exception
    logger.info("BitClient started")
    return logger
