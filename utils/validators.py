"""
Anime Subtitle Automation Tool v2.0 — Input Validators

Validation helpers that return validated values or raise on error.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from core.constants import VIDEO_EXTENSIONS, SUBTITLE_EXTENSIONS


def validate_folder_path(path_str: str) -> Path:
    """
    Validate folder path. Returns resolved Path or raises ValueError.
    """
    if not path_str or not path_str.strip():
        raise ValueError("Folder path is empty.")

    path = Path(path_str.strip())

    if not path.exists():
        raise ValueError(f"Folder does not exist: {path}")

    if not path.is_dir():
        raise ValueError(f"Path is not a directory: {path}")

    return path


def validate_series_name(name: str) -> str:
    """
    Validate series name. Returns cleaned name or raises ValueError.
    """
    if not name or not name.strip():
        raise ValueError("Series name is empty.")

    cleaned = name.strip()

    if len(cleaned) > 200:
        raise ValueError("Series name is too long (max 200 characters).")

    return cleaned


def validate_mkvtoolnix(path_str: str = None) -> bool:
    """
    Validate MKVToolNix installation. Returns True or raises ValueError.
    """
    from utils.paths import find_mkvtoolnix

    if path_str:
        path = Path(path_str.strip())
    else:
        found = find_mkvtoolnix()
        if not found:
            raise ValueError(
                "MKVToolNix not found. Please install it or set the path in settings."
            )
        path = Path(found)

    if not path.exists():
        raise ValueError(f"MKVToolNix directory not found: {path}")

    # Check for mkvmerge
    mkvmerge = path / "mkvmerge.exe"
    if not mkvmerge.exists():
        mkvmerge = path / "mkvmerge"
        if not mkvmerge.exists():
            raise ValueError(f"mkvmerge not found in: {path}")

    return True


def count_files_in_folder(folder: Path) -> dict[str, int]:
    """Count video and subtitle files in a folder."""
    videos = 0
    subtitles = 0

    try:
        for f in folder.iterdir():
            if f.is_file():
                ext = f.suffix.lower()
                if ext in VIDEO_EXTENSIONS:
                    videos += 1
                elif ext in SUBTITLE_EXTENSIONS:
                    subtitles += 1
    except OSError:
        pass

    return {"videos": videos, "subtitles": subtitles}
