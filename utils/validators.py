"""
Anime Subtitle Automation Tool v2.0 — Input Validators

Validation helpers that return validated values or raise on error.
"""

from __future__ import annotations

from pathlib import Path


def validate_folder_path(path_str: str) -> Path:
    """Validate a folder path. Returns it as an absolute, resolved Path or raises ValueError.

    Absolute on purpose: file names taken from a relative folder would reach
    mkvmerge as bare arguments.
    """
    if not path_str or not str(path_str).strip():
        raise ValueError("Folder path is empty.")

    path = Path(str(path_str).strip())

    if not path.exists():
        raise ValueError(f"Folder does not exist: {path}")

    if not path.is_dir():
        raise ValueError(f"Path is not a directory: {path}")

    return path.resolve()


def validate_mkvtoolnix(mkv_tools) -> str:
    """Check the mkvmerge the engine will really run (bundled copy included).

    Takes the engine's MKVToolsWrapper; returns the version line or raises ValueError.
    """
    ok, message = mkv_tools.validate_installation()
    if not ok:
        raise ValueError(message)
    return message
