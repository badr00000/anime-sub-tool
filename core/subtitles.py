"""
Anime Subtitle Automation Tool v2.0 — Subtitle file helpers

Character-set detection for text subtitles. Fansub SRT/ASS files are often saved
in a legacy code page (Windows-1256 for Arabic, Shift-JIS for Japanese, ...)
instead of UTF-8; mkvmerge assumes UTF-8 unless told otherwise (--sub-charset),
which turns the text into garbage symbols.

Encodings are named by a small set of ids used across the app ("utf-8",
"cp1256", "shift_jis", ...). python_codec() and mkvmerge_charset() translate an
id into what Python and mkvmerge (iconv) call it.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Optional

from core.constants import TEXT_SUBTITLE_EXTENSIONS
from utils.logger import get_logger

logger = get_logger(__name__)

CHARSET_AUTO = "auto"

# (label shown in the UI, id stored in ProcessingOptions.subtitle_charset)
CHARSET_CHOICES = [
    ("Auto-detect (recommended)", CHARSET_AUTO),
    ("UTF-8", "utf-8"),
    ("Windows-1256 (Arabic)", "cp1256"),
    ("Windows-1252 (Western)", "cp1252"),
    ("Shift-JIS (Japanese)", "shift_jis"),
    ("GB18030 (Chinese)", "gb18030"),
    ("Big5 (Traditional Chinese)", "big5"),
    ("EUC-KR (Korean)", "euc-kr"),
    ("UTF-16", "utf-16"),
]

_LABELS = {value: label for label, value in CHARSET_CHOICES if value != CHARSET_AUTO}
_LABELS.update({"utf-8-sig": "UTF-8 (BOM)", "utf-16-le": "UTF-16 LE (no BOM)",
                "utf-16-be": "UTF-16 BE (no BOM)", "utf-32": "UTF-32"})

# The Windows supersets are used for decoding: real files contain their extra
# characters (①, ～, ...) that the strict standards reject.
_PYTHON_CODECS = {"shift_jis": "cp932", "euc-kr": "cp949", "big5": "cp950"}
_MKVMERGE_NAMES = {"shift_jis": "CP932", "euc-kr": "CP949", "big5": "CP950",
                   "utf-16-le": "UTF-16LE", "utf-16-be": "UTF-16BE"}

# Thresholds for accepting a legacy code page (shares of the non-ASCII letters)
_ARABIC_LETTER_RATIO = 0.6     # Arabic letters after decoding as cp1256
_ARABIC_ALEF_RATIO = 0.05      # alef is ~13% of Arabic text, ~0% of anything misread
_HIRAGANA_RATIO = 0.2
_HANGUL_RATIO = 0.85
_COMMON_HANZI_RATIO = 0.25
_NON_LATIN_RATIO = 0.6
_CLUSTERED_RATIO = 0.5
_BINARY_CONTROL_RATIO = 0.02
_SAMPLE_BYTES = 262_144

_ALEFS = frozenset("اأإآ")

# The most frequent Chinese characters (simplified and traditional forms). Text
# decoded with the right code page is ~half made of these; the same bytes read
# with the wrong one give rare characters and almost never hit this set.
_COMMON_HANZI = frozenset(
    "的一是不了人我在有他这中大来上国个到说们为子和你地出道也时年得就那要下以生会自着去之过家学对可她里后小么心多天而能好都然没日于起还发成事只作当想看文无开手十用主行方又如前所本见经头面公同三已老从动两长知民样现分将外但身些与高意进把法此实回二理美点月明其种声全工己话儿者向情部正名定女问力机给等几很业最间新什打便位因重被走电四第门相次东政海口使教西再平真听世气信北少关并内加化由却代军产入先山五太水万市眼体别处总才场师书比住员九笑性通目华报立马命张活难神数件安表原车白应路期叫死常提感金何更反合放做系计或司利受光王果亲界及今京务制解各任至清物台象记边共风战干接它许八特觉望直服毛林题建南度统色字请交爱让认算论百吃义科怎元社术结六功指思非流每青管夫连远资队带花快条院变联言权往展该领传近留红治决周保达办运武半候七必城父强步完革深区即求品士转量空甚众技轻程告江语英基派满式李息写呢识极令黄德收脸钱党倒未持取设始版双历越史商千片容研像找友孩站广改议形委早房音火际则首单据导影失拿网香似斯专石若兵弟谁校读志飞观争究包组造落视济喜离虽坏吗啊吧呀哦嗯谢对别"
    "這來國個說們為時會著過學對後麼沒於還發當無開見經頭從動兩長樣現將與進實點種聲話兒問機給幾業間門東電氣關並內軍產萬體別處總場師書員華報馬張難數車應讓認論義術結連遠資隊帶條變聯權該領傳紅決達辦運強區轉輕語滿寫識極黃錢黨設雙歷廣議際則單據導網專誰讀飛觀爭組視濟離雖壞嗎謝妳愛聽覺親邊風戰許請題統計係"
)


def python_codec(encoding: str) -> str:
    return _PYTHON_CODECS.get(encoding, encoding)


def mkvmerge_charset(encoding: str) -> str:
    """Name of an encoding id as mkvmerge's iconv expects it."""
    if encoding in _MKVMERGE_NAMES:
        return _MKVMERGE_NAMES[encoding]
    if encoding.startswith("iso8859_"):                 # Python 'iso8859_2' -> 'ISO-8859-2'
        return "ISO-8859-" + encoding[len("iso8859_"):]
    return encoding


def describe_encoding(encoding: Optional[str]) -> str:
    """Human-readable name: 'cp1256' -> 'Windows-1256 (Arabic)'."""
    if not encoding:
        return "Unknown (not text?)"
    return _LABELS.get(encoding, encoding.upper())


# ── detection ─────────────────────────────────────────────────────────────────

def _bom_encoding(data: bytes) -> Optional[str]:
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if data.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        return "utf-32"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    return None


def _looks_binary(data: bytes) -> bool:
    """Text has (almost) no control bytes other than tab / newlines."""
    sample = data[:_SAMPLE_BYTES]
    if not sample:
        return False
    controls = sum(1 for b in sample if (b < 32 and b not in (9, 10, 12, 13, 27)) or b == 127)
    return controls / len(sample) > _BINARY_CONTROL_RATIO


def _utf16_without_bom(data: bytes) -> Optional[str]:
    """UTF-16 text is recognisable by its NUL bytes: every ASCII character (digits,
    timestamps, tags, line breaks) has one, always on the same side."""
    sample = data[:8192]
    if len(sample) < 4 or len(data) % 2:
        return None
    even, odd = sample[0::2], sample[1::2]
    even_nul, odd_nul = even.count(0) / len(even), odd.count(0) / len(odd)
    if odd_nul > 0.3 and even_nul < 0.05:
        encoding = "utf-16-le"
    elif even_nul > 0.3 and odd_nul < 0.05:
        encoding = "utf-16-be"
    else:
        return None
    try:
        text = data.decode(encoding)
    except UnicodeDecodeError:
        return None
    return None if _looks_binary(text.encode("utf-8", errors="replace")) else encoding


def _foreign_letters(text: str) -> list[str]:
    """The non-ASCII letters. ASCII is ignored on purpose: subtitle files are full
    of English tags, style names and romaji that say nothing about the encoding."""
    return [c for c in text if ord(c) > 127 and c.isalpha()]


def _strict(data: bytes, codec: str) -> Optional[str]:
    try:
        return data.decode(codec)
    except (UnicodeDecodeError, LookupError):
        return None


def _detect_cjk(data: bytes) -> Optional[str]:
    """Shift-JIS / EUC-KR / GB18030 / Big5: the bytes must decode strictly AND give
    the letters that language is really written with. Decoding alone proves nothing:
    these code pages accept almost any byte pair."""
    text = _strict(data, "cp932")
    if text is not None:
        letters = _foreign_letters(text)
        hiragana = sum(1 for c in letters if "぀" <= c <= "ゟ")
        if letters and hiragana / len(letters) >= _HIRAGANA_RATIO:
            return "shift_jis"

    text = _strict(data, "cp949")
    if text is not None:
        letters = _foreign_letters(text)
        hangul = sum(1 for c in letters if "가" <= c <= "힣")
        if letters and hangul / len(letters) >= _HANGUL_RATIO:
            return "euc-kr"

    best, best_score = None, 0.0
    for encoding, codec in (("gb18030", "gb18030"), ("big5", "cp950")):
        text = _strict(data, codec)
        if text is None:
            continue
        hanzi = [c for c in _foreign_letters(text) if "一" <= c <= "鿿"]
        if not hanzi:
            continue
        score = sum(1 for c in hanzi if c in _COMMON_HANZI) / len(hanzi)
        if score > best_score:
            best, best_score = encoding, score
    return best if best_score >= _COMMON_HANZI_RATIO else None


def _is_arabic_cp1256(data: bytes) -> bool:
    text = _strict(data, "cp1256")
    if text is None:
        return False
    letters = _foreign_letters(text)
    if not letters:
        return False
    arabic = sum(1 for c in letters if "؀" <= c <= "ۿ")
    alefs = sum(1 for c in letters if c in _ALEFS)
    # The alef test keeps out Western text: in cp1256 'ä', 'á', 'ß' read as Arabic
    # letters, so German or Spanish can pass the ratio alone.
    return (arabic / len(letters) >= _ARABIC_LETTER_RATIO
            and alefs / len(letters) >= _ARABIC_ALEF_RATIO)


def _clustered_high_bytes(data: bytes) -> float:
    """Share of the non-ASCII bytes that sit next to another one. Scripts written
    entirely in high bytes (Cyrillic, Greek, Hebrew) score ~1; Western text, where
    accented letters stand alone between ASCII letters, scores ~0."""
    sample = data[:_SAMPLE_BYTES]
    high = [i for i, b in enumerate(sample) if b >= 0x80]
    if not high:
        return 0.0
    last = len(sample) - 1
    clustered = sum(1 for i in high
                    if (i > 0 and sample[i - 1] >= 0x80) or (i < last and sample[i + 1] >= 0x80))
    return clustered / len(high)


def _symbols_inside_words(text: str) -> float:
    """Share of the non-ASCII characters that are symbols wedged between two letters
    ('¹', '³', '¿' inside a word): what Central European text looks like read as cp1252."""
    high = [i for i, c in enumerate(text) if ord(c) > 127]
    if not high:
        return 0.0
    last = len(text) - 1
    wedged = sum(1 for i in high
                 if not text[i].isalpha() and 0 < i < last
                 and text[i - 1].isalpha() and text[i + 1].isalpha())
    return wedged / len(high)


def _normalizer_guess(data: bytes) -> Optional[tuple[str, str]]:
    try:
        from charset_normalizer import from_bytes
    except ImportError:
        return None
    try:
        best = from_bytes(data[:_SAMPLE_BYTES]).best()
    except Exception:
        return None
    if best is None or not best.encoding:
        return None
    return best.encoding, str(best)


def _detect_single_byte(data: bytes) -> Optional[str]:
    """Western fallback. cp1252 wins unless there is real evidence against it:
    charset_normalizer alone readily calls French 'cp1250' or 'cp1257'."""
    as_cp1252 = _strict(data, "cp1252")
    guess = _normalizer_guess(data)
    if guess:
        encoding, text = guess
        if encoding not in ("cp1252", "latin_1", "iso8859_15", "ascii", "utf_8"):
            letters = _foreign_letters(text)
            non_latin = sum(1 for c in letters
                            if not unicodedata.name(c, "").startswith("LATIN"))
            if (letters and non_latin / len(letters) >= _NON_LATIN_RATIO
                    and _clustered_high_bytes(data) >= _CLUSTERED_RATIO):
                return encoding
            if (encoding in ("cp1250", "iso8859_2") and as_cp1252 is not None
                    and _symbols_inside_words(as_cp1252) >= 0.1):
                return encoding
    if as_cp1252 is not None:
        return "cp1252"
    return guess[0] if guess else None


def detect_encoding(data: bytes) -> Optional[str]:
    """Encoding id of subtitle bytes, or None when the data is not text.

    Order: BOM -> UTF-16 without BOM -> strict UTF-8 -> CJK code pages ->
    Arabic Windows-1256 -> Western fallback.
    """
    bom = _bom_encoding(data)
    if bom:
        return bom
    utf16 = _utf16_without_bom(data)
    if utf16:
        return utf16
    if _looks_binary(data):
        return None
    if _strict(data, "utf-8") is not None:
        return "utf-8"
    cjk = _detect_cjk(data)
    if cjk:
        return cjk
    if _is_arabic_cp1256(data):
        return "cp1256"
    return _detect_single_byte(data)


def detect_file_encoding(path: Path) -> Optional[str]:
    """detect_encoding() for a file; None when unreadable or not text."""
    try:
        data = Path(path).read_bytes()
    except OSError as e:
        logger.warning(f"Could not read subtitle {path} for charset detection: {e}")
        return None
    return detect_encoding(data)


def detect_charset(path: Path) -> Optional[str]:
    """The encoding id mkvmerge must be told about, or None when no flag is needed
    (UTF-8, any BOM) or when the file is not text at all."""
    encoding = detect_file_encoding(path)
    if encoding is None:
        logger.warning(f"{Path(path).name} does not look like a text file; no encoding passed.")
        return None
    if encoding in ("utf-8", "utf-8-sig", "utf-16", "utf-32"):   # mkvmerge reads BOMs itself
        return None
    return encoding


def resolve_charset(path: Path, setting: str) -> Optional[str]:
    """Turn the user's setting ('auto', '' or an explicit charset) into the value
    for mkvmerge's --sub-charset, or None when no flag is needed."""
    if Path(path).suffix.lower() not in TEXT_SUBTITLE_EXTENSIONS:
        return None
    setting = (setting or "").strip()
    if not setting:
        return None
    key = setting.lower().replace("_", "-")
    if key == CHARSET_AUTO:
        charset = detect_charset(path)
        if charset:
            logger.info(f"Detected subtitle encoding {charset} for {Path(path).name}")
        return mkvmerge_charset(charset) if charset else None
    if key in ("utf-8", "utf8"):
        return None
    if key in ("utf-16", "utf16"):
        # With a BOM mkvmerge finds the byte order itself; without one it has to be told.
        detected = detect_file_encoding(path)
        if detected in ("utf-16", "utf-8-sig", "utf-32"):
            return None
        return mkvmerge_charset(detected if detected in ("utf-16-le", "utf-16-be") else "utf-16-le")
    known = {"shift-jis": "shift_jis", "sjis": "shift_jis", "euckr": "euc-kr"}.get(key, key)
    return mkvmerge_charset(known) if known in _LABELS else setting
