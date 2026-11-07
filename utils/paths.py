"""
Anime Subtitle Automation Tool v2.0 — Path Utilities

MKVToolNix discovery, filename sanitization, output path generation,
and PyInstaller-compatible binary path resolution.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path
from typing import Optional

from core.constants import (
    CONFIG_DIR_NAME,
    MKVMERGE_EXE,
    MKVPROPEDIT_EXE,
    MKVTOOLNIX_DEFAULT_PATHS,
)


def find_mkvtoolnix() -> Optional[str]:
    """Auto-discover MKVToolNix installation path."""
    mkvmerge_path = shutil.which("mkvmerge")
    if mkvmerge_path:
        return str(Path(mkvmerge_path).parent)

    for search_path in MKVTOOLNIX_DEFAULT_PATHS:
        mkvmerge = Path(search_path) / MKVMERGE_EXE
        if mkvmerge.exists():
            return search_path

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundle_dir = Path(sys._MEIPASS)
        if (bundle_dir / MKVMERGE_EXE).exists():
            return str(bundle_dir)

    return None


def get_binary_path(binary_name: str, mkvtoolnix_path: Optional[str] = None) -> str:
    """Resolve full path to an MKVToolNix binary."""
    if mkvtoolnix_path:
        full_path = Path(mkvtoolnix_path) / binary_name
        if full_path.exists():
            return str(full_path)

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        full_path = Path(sys._MEIPASS) / binary_name
        if full_path.exists():
            return str(full_path)

    discovered = find_mkvtoolnix()
    if discovered:
        full_path = Path(discovered) / binary_name
        if full_path.exists():
            return str(full_path)

    which_path = shutil.which(binary_name.replace(".exe", ""))
    if which_path:
        return which_path

    raise FileNotFoundError(
        f"Could not find {binary_name}. "
        f"Please install MKVToolNix or set the path in settings."
    )


def get_app_data_dir() -> Path:
    """Get the application data directory."""
    app_dir = Path.home() / CONFIG_DIR_NAME
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def sanitize_filename(name: str, replacement: str = "_") -> str:
    """Clean a filename by removing invalid characters."""
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, replacement, name)
    sanitized = sanitized.strip(" .")
    sanitized = re.sub(r'\s+', ' ', sanitized)
    sanitized = re.sub(r'_+', '_', sanitized)
    if not sanitized:
        sanitized = "unnamed"
    return sanitized


def generate_output_filename(original_name: str, suffix: str = "PROCESSED") -> str:
    """
    Generate output filename from original.

    Given "video.mkv" and suffix "PROCESSED", returns "video [PROCESSED].mkv"
    """
    path = Path(original_name)
    stem = path.stem
    ext = path.suffix or ".mkv"

    if suffix:
        return f"{stem} [{suffix}]{ext}"
    return f"{stem}{ext}"


def ensure_output_dir(source_folder: Path, subfolder_name: str = "PROCESSED") -> Path:
    """Ensure the output directory exists and return its path."""
    output_dir = source_folder / subfolder_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir
