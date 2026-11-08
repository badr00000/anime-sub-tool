"""
Anime Subtitle Automation Tool v2.0 — Subtitle file helpers

Character-set detection for text subtitles. Arabic SRT/ASS files are often saved
as Windows-1256 instead of UTF-8; mkvmerge assumes UTF-8 unless told otherwise
(--sub-charset), which turns the Arabic text into garbage symbols.
"""

from pathlib import Path
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)

# Only text subtitle formats have a character set mkvmerge can convert.
TEXT_SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa"}

CHARSET_AUTO = "auto"

# How much of the file must be Arabic letters (after decoding as cp1256)
# before we trust that it really is an Arabic Windows-1256 file.
_ARABIC_LETTER_RATIO = 0.6


def _arabic_ratio(text: str) -> float:
    """Share of Arabic among the NON-ASCII letters.

    ASCII is ignored on purpose: SRT/ASS files are full of English tags, style
    names and romaji that would otherwise hide a fully Arabic file. A Western
    cp1252 file decoded as cp1256 gives é/ü/à (not Arabic), so it stays low.
    """
    letters = [c for c in text if c.isalpha() and ord(c) > 127]
    if not letters:
        return 0.0
    arabic = sum(1 for c in letters if "؀" <= c <= "ۿ")
    return arabic / len(letters)


def detect_charset(path: Path) -> Optional[str]:
    """Return the charset to pass to mkvmerge, or None when UTF-8/BOM (no flag needed).

    Order: BOM -> valid UTF-8 -> Arabic Windows-1256 -> charset_normalizer (if installed).
    """
    try:
        data = Path(path).read_bytes()
    except OSError as e:
        logger.warning(f"Could not read subtitle {path} for charset detection: {e}")
        return None

    # mkvmerge reads BOMs by itself
    if data.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")):
        return None

    try:
        data.decode("utf-8")
        return None
    except UnicodeDecodeError:
        pass

    if _arabic_ratio(data.decode("cp1256", errors="replace")) >= _ARABIC_LETTER_RATIO:
        return "cp1256"

    try:
        from charset_normalizer import from_bytes
    except ImportError:
        logger.warning(f"Unknown encoding for {Path(path).name}; install charset-normalizer for better detection.")
        return None

    best = from_bytes(data).best()
    if best is None:
        logger.warning(f"Could not detect the encoding of {Path(path).name}; passing it as-is.")
        return None
    return best.encoding


def resolve_charset(path: Path, setting: str) -> Optional[str]:
    """Turn the user's setting ('auto', '' or an explicit charset) into a mkvmerge charset."""
    if Path(path).suffix.lower() not in TEXT_SUBTITLE_EXTENSIONS:
        return None
    setting = (setting or "").strip()
    if not setting:
        return None
    if setting.lower() == CHARSET_AUTO:
        charset = detect_charset(path)
        if charset:
            logger.info(f"Detected subtitle encoding {charset} for {Path(path).name}")
        return charset
    if setting.lower().replace("-", "") == "utf8":
        return None
    return setting
