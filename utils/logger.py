"""
Anime Subtitle Automation Tool v2.0 — Logger

Dual-output logging: file + console. Thread-safe with per-session log files.
Provides a callback-based log handler for real-time GUI log panel updates.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from core.constants import CONFIG_DIR_NAME, LOG_DIR_NAME, APP_NAME


class GUILogHandler(logging.Handler):
    """
    Custom log handler that forwards log records to a callback function.
    Used to send log messages to the GUI log panel in real-time.
    """

    def __init__(self, callback: Callable[[str, str], None]):
        """
        Args:
            callback: Function(message: str, level: str) called for each log record.
        """
        super().__init__()
        self.callback = callback

    def emit(self, record: logging.LogRecord):
        try:
            message = self.format(record)
            level = record.levelname.lower()
            self.callback(message, level)
        except Exception:
            self.handleError(record)


def _get_log_dir() -> Path:
    """Get the log directory path."""
    home = Path.home()
    log_dir = home / CONFIG_DIR_NAME / LOG_DIR_NAME
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logger(
    name: str = APP_NAME,
    level: int = logging.DEBUG,
    gui_callback: Optional[Callable[[str, str], None]] = None,
    log_to_file: bool = True,
    log_to_console: bool = True,
) -> logging.Logger:
    """
    Set up and return a configured logger instance.

    Args:
        name: Logger name
        level: Logging level
        gui_callback: Optional callback for GUI log panel updates
        log_to_file: Whether to write logs to a file
        log_to_console: Whether to print logs to console

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers on repeated calls
    if logger.handlers:
        logger.handlers.clear()

    logger.setLevel(level)
    logger.propagate = False

    # Log format
    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )
    gui_formatter = logging.Formatter(
        fmt="[%(asctime)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # File handler — one log file per session
    if log_to_file:
        try:
            log_dir = _get_log_dir()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = log_dir / f"session_{timestamp}.log"

            file_handler = logging.FileHandler(
                str(log_file), encoding="utf-8"
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except OSError:
            pass  # Skip file logging if directory is not writable

    # Console handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    # GUI callback handler
    if gui_callback:
        gui_handler = GUILogHandler(gui_callback)
        gui_handler.setLevel(logging.INFO)
        gui_handler.setFormatter(gui_formatter)
        logger.addHandler(gui_handler)

    return logger


def get_logger(name: str = APP_NAME) -> logging.Logger:
    """Get an existing logger by name, or create a basic one."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name, log_to_file=False)
    return logger
