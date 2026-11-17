"""
Anime Subtitle Automation Tool v2.0 — Logger

Every module logs to a child of one "anime-sub-tool" logger. setup_logging()
attaches a size-capped rotating file (and optionally the console) to it once.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from core.constants import (
    APP_ID, LOG_BACKUP_COUNT, LOG_DIR_NAME, LOG_FILE_NAME, LOG_MAX_BYTES,
)

ROOT_LOGGER = APP_ID


def get_logger(name: str = "") -> logging.Logger:
    """Logger for a module: a child of the app's root logger, never with its own handlers."""
    if not name or name == ROOT_LOGGER:
        return logging.getLogger(ROOT_LOGGER)
    return logging.getLogger(f"{ROOT_LOGGER}.{name}")


def setup_logging(console: bool = False, level: int = logging.DEBUG) -> logging.Logger:
    """Configure the app's root logger. Safe to call more than once."""
    from utils.paths import get_app_data_dir

    root = logging.getLogger(ROOT_LOGGER)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    root.setLevel(level)
    root.propagate = False

    try:
        log_dir = get_app_data_dir() / LOG_DIR_NAME
        log_dir.mkdir(parents=True, exist_ok=True)
        # delay=True: the file is only created when something is actually logged
        file_handler = RotatingFileHandler(
            str(log_dir / LOG_FILE_NAME), maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT, encoding="utf-8", delay=True,
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)-8s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
        root.addHandler(file_handler)
    except OSError:
        pass  # no file logging when the folder is not writable

    # A windowed .exe has no stderr at all
    if console and sys.stderr is not None:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        console_handler.addFilter(lambda record: not getattr(record, "echoed", False))
        root.addHandler(console_handler)

    if not root.handlers:
        root.addHandler(logging.NullHandler())
    return root
