"""
Anime Subtitle Automation Tool v2.0 — Constants & Defaults

Central location for all magic strings, supported formats, language codes,
and default values used throughout the application.
"""

from pathlib import Path

# ──────────────────────────────────────────────────────────────
# Application Info
# ──────────────────────────────────────────────────────────────

APP_NAME = "Anime Subtitle Automation Tool"
APP_VERSION = "2.0.0"
APP_AUTHOR = "AnimeSubTool"
APP_ID = "anime-sub-tool"

# ──────────────────────────────────────────────────────────────
# Supported File Formats
# ──────────────────────────────────────────────────────────────

VIDEO_EXTENSIONS = frozenset({
    ".mkv", ".mp4", ".webm", ".avi",
    ".m4v", ".mov", ".ts", ".m2ts",
})

SUBTITLE_EXTENSIONS = frozenset({
    ".ass", ".ssa",   # Advanced SubStation Alpha / SubStation Alpha
    ".srt",           # SubRip
    ".vtt",           # WebVTT
    ".sub",           # VobSub / MicroDVD
    ".idx",           # VobSub index
})

# Text subtitles whose character set can be detected/converted and whose timing
# the Sync tool can shift.
TEXT_SUBTITLE_EXTENSIONS = frozenset({".ass", ".ssa", ".srt"})

# Outputs written next to their sources carry this marker so the scanner never
# picks them up again as episodes.
OUTPUT_MARKER = "[AnimeSubTool]"

# mkvmerge exit codes
MKVMERGE_SUCCESS = 0
MKVMERGE_WARNING = 1
MKVMERGE_ERROR = 2

MKVTOOLNIX_DEFAULT_PATHS = [
    r"C:\Program Files\MKVToolNix",
    r"C:\Program Files (x86)\MKVToolNix",
    "/usr/bin",
    "/usr/local/bin",
]

# ──────────────────────────────────────────────────────────────
# Processing Defaults
# ──────────────────────────────────────────────────────────────

DEFAULT_OUTPUT_SUBFOLDER = "PROCESSED"
DEFAULT_PARALLEL_WORKERS = 4
MAX_PARALLEL_WORKERS = 8
MIN_PARALLEL_WORKERS = 1

# ──────────────────────────────────────────────────────────────
# Filename Patterns (Regex)
# ──────────────────────────────────────────────────────────────

# Common anime filename patterns for episode number extraction
# These are fallbacks when anitopy fails to parse
EPISODE_PATTERNS = [
    # [Group] Title - 01 [Quality]
    r'[-–]\s*(\d{1,4})(?:v\d+)?\s*[\[\(]',
    # [Group] Title - 01
    r'[-–]\s*(\d{1,4})(?:v\d+)?\s*(?:\.|$)',
    # S01E01 or S1E1
    # (season is non-capturing so group(1) is always the episode)
    r'[Ss]\d{1,2}[Ee](\d{1,4})',
    # EP01 or Ep.01
    r'[Ee][Pp]\.?\s*(\d{1,4})',
    # Episode 01
    r'[Ee]pisode\s*(\d{1,4})',
    # _01_ or _01.
    r'_(\d{1,4})(?:v\d+)?[_\.]',
    # Bare number at end: Title 01.mkv
    r'\s(\d{1,4})(?:v\d+)?\s*\.\w+$',
    # Bare number with space: Title 01 [info]
    r'\s(\d{1,4})(?:v\d+)?\s*[\[\(]',
]

# ──────────────────────────────────────────────────────────────
# UI Constants
# ──────────────────────────────────────────────────────────────

# Minimum window size
MIN_WINDOW_WIDTH = 900
MIN_WINDOW_HEIGHT = 650

# Default window size
DEFAULT_WINDOW_WIDTH = 1100
DEFAULT_WINDOW_HEIGHT = 750

# Log panel max lines
LOG_MAX_LINES = 5000

# ──────────────────────────────────────────────────────────────
# Configuration File
# ──────────────────────────────────────────────────────────────

CONFIG_DIR_NAME = ".anime-sub-tool"
CONFIG_FILE_NAME = "config.json"
LOG_DIR_NAME = "logs"
LOG_FILE_NAME = "anime-sub-tool.log"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3
