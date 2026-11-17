"""
Anime Subtitle Automation Tool v2.0 — Path Utilities

Bundle-aware resource lookup, the app data directory and output path rules.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from core.constants import CONFIG_DIR_NAME, OUTPUT_MARKER


def resource_path(*parts: str) -> Path:
    """A file shipped with the app: inside the PyInstaller bundle, or the repo root from source."""
    if hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent
    return base.joinpath(*parts)


def get_app_data_dir() -> Path:
    """Folder holding config.json and logs. Not created here."""
    return Path.home() / CONFIG_DIR_NAME


def is_tool_output(path: Path) -> bool:
    """True for a file this tool wrote next to its sources ('name [AnimeSubTool].mkv')."""
    return Path(path).stem.rstrip().endswith(OUTPUT_MARKER)


def resolve_output_dir(source_folder: Path, output_dir: Optional[Path],
                       create_output_folder: bool, output_folder: str) -> Path:
    """Where processed files of `source_folder` go. Pure computation."""
    if output_dir:
        return Path(output_dir).resolve()
    source_folder = Path(source_folder).resolve()
    if create_output_folder and output_folder:
        return (source_folder / output_folder).resolve()
    return source_folder


def output_filename(video_name: str, same_folder: bool) -> str:
    """Output name for an episode. Always .mkv: mkvmerge writes Matroska whatever
    the input was. In the source folder itself the name gets the output marker."""
    stem = Path(video_name).stem
    if same_folder:
        return f"{stem} {OUTPUT_MARKER}.mkv"
    return f"{stem}.mkv"
