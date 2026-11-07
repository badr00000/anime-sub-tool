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

# Subtitle formats that are text-based (can be inspected/edited)
TEXT_SUBTITLE_EXTENSIONS = frozenset({
    ".ass", ".ssa", ".srt", ".vtt",
})

# ──────────────────────────────────────────────────────────────
# Language Codes (ISO 639-2 / BCP 47)
# ──────────────────────────────────────────────────────────────

JAPANESE_LANGUAGE_CODES = frozenset({
    # ISO 639-2
    "jpn", "ja", "jp",
    # IETF BCP 47 prefixes
    "ja-jp", "ja-jpn",
})

ARABIC_LANGUAGE_CODES = frozenset({
    # ISO 639-2
    "ara", "ar",
    # IETF BCP 47 prefixes
    "ar-eg", "ar-sa", "ar-ae",
})

# Default language settings for embedding
DEFAULT_SUBTITLE_LANGUAGE = "ara"       # ISO 639-2 for Arabic
DEFAULT_SUBTITLE_NAME = "Arabic"
DEFAULT_AUDIO_LANGUAGE = "jpn"          # ISO 639-2 for Japanese

# Language code for "undetermined" — some anime files use this
UNDETERMINED_LANGUAGE = "und"

# ──────────────────────────────────────────────────────────────
# MKVToolNix
# ──────────────────────────────────────────────────────────────

MKVTOOLNIX_DEFAULT_PATHS = [
    r"C:\Program Files\MKVToolNix",
    r"C:\Program Files (x86)\MKVToolNix",
    r"/usr/bin",
    r"/usr/local/bin",
]

MKVMERGE_EXE = "mkvmerge.exe"
MKVPROPEDIT_EXE = "mkvpropedit.exe"
MKVINFO_EXE = "mkvinfo.exe"

# mkvmerge exit codes
MKVMERGE_SUCCESS = 0
MKVMERGE_WARNING = 1
MKVMERGE_ERROR = 2

# ──────────────────────────────────────────────────────────────
# Processing Defaults
# ──────────────────────────────────────────────────────────────

DEFAULT_OUTPUT_SUBFOLDER = "PROCESSED"
DEFAULT_PARALLEL_WORKERS = 4
MAX_PARALLEL_WORKERS = 8
MIN_PARALLEL_WORKERS = 1

# Estimated processing time per episode (seconds) — for ETA calculation
ESTIMATED_SECONDS_PER_EPISODE = 5.0

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
    r'[Ss](\d{1,2})[Ee](\d{1,4})',
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

# Characters to strip when normalizing series names
FILENAME_STRIP_CHARS = set('[](){}!@#$%^&*+=|\\/<>?~`')

# ──────────────────────────────────────────────────────────────
# UI Constants
# ──────────────────────────────────────────────────────────────

# Minimum window size
MIN_WINDOW_WIDTH = 900
MIN_WINDOW_HEIGHT = 650

# Default window size
DEFAULT_WINDOW_WIDTH = 1100
DEFAULT_WINDOW_HEIGHT = 750

# Progress update interval (milliseconds)
PROGRESS_UPDATE_INTERVAL_MS = 100

# Log panel max lines
LOG_MAX_LINES = 5000

# ──────────────────────────────────────────────────────────────
# Configuration File
# ──────────────────────────────────────────────────────────────

CONFIG_DIR_NAME = ".anime-sub-tool"
CONFIG_FILE_NAME = "config.json"
LOG_DIR_NAME = "logs"
