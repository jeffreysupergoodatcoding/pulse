"""
Structured logging setup for Pulse.
All modules should import logger from here.
"""
import logging
import sys
from datetime import datetime, timezone


class _UTCFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()

    def format(self, record):
        record.levelname = record.levelname.ljust(8)
        return super().format(record)


def _build_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = _UTCFormatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a named logger with structured UTC formatting."""
    return _build_logger(f"pulse.{name}")


# Root pulse logger
logger = get_logger("core")
