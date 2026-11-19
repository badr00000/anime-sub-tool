"""
Anime Subtitle Automation Tool v2.0 — Subtitle file helpers

Character-set detection for text subtitles. Fansub SRT/ASS files are often saved
in a legacy code page (Windows-1256 for Arabic, Shift-JIS for Japanese, ...)
instead of UTF-8; mkvmerge assumes UTF-8 unless told otherwise (--sub-charset),
which turns the text into garbage symbols.

Encodings are named by a small set of ids used across the app ("utf-8",
"cp1256", "shift_jis", ...). python_codec() and mkvmerge_charset() translate an
id into what Python and mkvmerge (iconv) call it.

Detection does not guess: when the bytes do not clearly identify one code page
the result is ENCODING_UNCERTAIN, no --sub-charset is passed and the user is
asked to pick the encoding.
"""

from __future__ import annotations

import codecs
import math
import unicodedata
from pathlib import Path
from typing import Optional

from core.constants import TEXT_SUBTITLE_EXTENSIONS
from utils.logger import get_logger

logger = get_logger(__name__)

CHARSET_AUTO = "auto"
# Text, but no single code page clearly fits: the user has to choose
ENCODING_UNCERTAIN = "uncertain"
UNCERTAIN_HINT = "encoding uncertain — choose it in Encoding"

# (label shown in the UI, id stored in ProcessingOptions.subtitle_charset)
CHARSET_CHOICES = [
    ("Auto-detect (recommended)", CHARSET_AUTO),
    ("UTF-8", "utf-8"),
    ("Windows-1256 (Arabic)", "cp1256"),
    ("Windows-1252 (Western)", "cp1252"),
    ("Windows-1250 (Central European)", "cp1250"),
    ("Windows-1254 (Turkish)", "cp1254"),
    ("Windows-1258 (Vietnamese)", "cp1258"),
    ("Windows-1251 (Cyrillic)", "cp1251"),
    ("KOI8-R (Russian)", "koi8_r"),
    ("Windows-1253 (Greek)", "cp1253"),
    ("Windows-1255 (Hebrew)", "cp1255"),
    ("Windows-874 (Thai)", "cp874"),
    ("Shift-JIS (Japanese)", "shift_jis"),
    ("GB18030 (Chinese)", "gb18030"),
    ("Big5 (Traditional Chinese)", "big5"),
    ("EUC-KR (Korean)", "euc-kr"),
    ("UTF-16", "utf-16"),
]

_LABELS = {value: label for label, value in CHARSET_CHOICES if value != CHARSET_AUTO}
_LABELS.update({"utf-8-sig": "UTF-8 (BOM)", "utf-16-le": "UTF-16 LE (no BOM)",
                "utf-16-be": "UTF-16 BE (no BOM)", "utf-32": "UTF-32",
                ENCODING_UNCERTAIN: f"⚠ Uncertain — {UNCERTAIN_HINT.split(' — ')[1]}"})

# The Windows supersets are used for decoding: real files contain their extra
# characters (①, ～, ...) that the strict standards reject. An uncertain file is
# shown as UTF-8 so the broken characters are visible as '�'.
_PYTHON_CODECS = {"shift_jis": "cp932", "euc-kr": "cp949", "big5": "cp950",
                  ENCODING_UNCERTAIN: "utf-8"}

# The only names ever handed to mkvmerge: Python codec name (as codecs.lookup()
# spells it, with '-' for '_') -> the name mkvmerge's iconv accepts.
_ICONV_NAMES = {
    "shift-jis": "CP932", "cp932": "CP932", "euc-kr": "CP949", "cp949": "CP949",
    "big5": "CP950", "cp950": "CP950", "big5hkscs": "BIG5-HKSCS",
    "gb18030": "GB18030", "gbk": "GBK", "gb2312": "GB2312", "euc-jp": "EUC-JP",
    "utf-8": "UTF-8", "utf-16": "UTF-16", "utf-16-le": "UTF-16LE", "utf-16-be": "UTF-16BE",
    "utf-32": "UTF-32", "koi8-r": "KOI8-R", "koi8-u": "KOI8-U", "mac-cyrillic": "MACCYRILLIC",
    "cp866": "CP866", "cp874": "CP874", "tis-620": "TIS-620", "latin-1": "ISO-8859-1",
    **{f"cp{n}": f"CP{n}" for n in range(1250, 1259)},
    **{f"iso8859-{n}": f"ISO-8859-{n}"
       for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16)},
}


def python_codec(encoding: str) -> str:
    return _PYTHON_CODECS.get(encoding, encoding)


def mkvmerge_charset(encoding: Optional[str]) -> Optional[str]:
    """Name of an encoding as mkvmerge's iconv expects it; None when it is not
    in the table of names mkvmerge is known to accept."""
    if not encoding or encoding == ENCODING_UNCERTAIN:
        return None
    key = encoding.strip().lower().replace("_", "-")
    if key in _ICONV_NAMES:
        return _ICONV_NAMES[key]
    try:
        key = codecs.lookup(encoding.strip()).name.replace("_", "-")
    except LookupError:
        return None
    return _ICONV_NAMES.get(key)


def describe_encoding(encoding: Optional[str]) -> str:
    """Human-readable name: 'cp1256' -> 'Windows-1256 (Arabic)'."""
    if not encoding:
        return "Unknown (not text?)"
    return _LABELS.get(encoding, encoding.upper())


def is_uncertain(id_or_description: Optional[str]) -> bool:
    """True for ENCODING_UNCERTAIN and for its describe_encoding() text."""
    return id_or_description in (ENCODING_UNCERTAIN, _LABELS[ENCODING_UNCERTAIN])


# ── detection ─────────────────────────────────────────────────────────────────

_BINARY_CONTROL_RATIO = 0.02
_SAMPLE_BYTES = 262_144


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


# Fewest non-ASCII letters any guess needs. Two or three characters decode as
# something plausible in almost every code page ('Да' is valid Korean bytes).
_MIN_EVIDENCE = 8

_HIRAGANA_RATIO = 0.2
_HANGUL_RATIO = 0.85
_COMMON_HANZI_RATIO = 0.25

# The most frequent Chinese characters (simplified and traditional forms). Text
# decoded with the right code page is ~half made of these; the same bytes read
# with the wrong one give rare characters and almost never hit this set.
_COMMON_HANZI = frozenset(
    "的一是不了人我在有他这中大来上国个到说们为子和你地出道也时年得就那要下以生会自着去之过家学对可她里后小么心多天而能好都然没日于起还发成事只作当想看文无开手十用主行方又如前所本见经头面公同三已老从动两长知民样现分将外但身些与高意进把法此实回二理美点月明其种声全工己话儿者向情部正名定女问力机给等几很业最间新什打便位因重被走电四第门相次东政海口使教西再平真听世气信北少关并内加化由却代军产入先山五太水万市眼体别处总才场师书比住员九笑性通目华报立马命张活难神数件安表原车白应路期叫死常提感金何更反合放做系计或司利受光王果亲界及今京务制解各任至清物台象记边共风战干接它许八特觉望直服毛林题建南度统色字请交爱让认算论百吃义科怎元社术结六功指思非流每青管夫连远资队带花快条院变联言权往展该领传近留红治决周保达办运武半候七必城父强步完革深区即求品士转量空甚众技轻程告江语英基派满式李息写呢识极令黄德收脸钱党倒未持取设始版双历越史商千片容研像找友孩站广改议形委早房音火际则首单据导影失拿网香似斯专石若兵弟谁校读志飞观争究包组造落视济喜离虽坏吗啊吧呀哦嗯谢对别"
    "這來國個說們為時會著過學對後麼沒於還發當無開見經頭從動兩長樣現將與進實點種聲話兒問機給幾業間門東電氣關並內軍產萬體別處總場師書員華報馬張難數車應讓認論義術結連遠資隊帶條變聯權該領傳紅決達辦運強區轉輕語滿寫識極黃錢黨設雙歷廣議際則單據導網專誰讀飛觀爭組視濟離雖壞嗎謝妳愛聽覺親邊風戰許請題統計係"
)


# Double-byte code pages accept an ASCII byte (0x40-0x7E) as the second byte of a
# character. Western text in Windows-1252 is full of such pairs: ’ (0x92) followed
# by a letter ("I’m", "don’t") is a valid Korean syllable in CP949 and a valid
# character in GBK. Real Korean (lead 0xB0-0xC8, trail 0xA1-0xFE) and simplified
# Chinese (GB2312) almost never use an ASCII trail byte; Japanese katakana and
# Big5 do for part of their characters, so they get a higher limit.
_MAX_ASCII_TRAIL_SHARE = {"shift_jis": 0.75, "euc-kr": 0.3, "gb18030": 0.3, "big5": 0.75}
# Fewer CJK characters than this is weak evidence: a Western code page that reads
# the file cleanly is then preferred.
_STRONG_CJK_EVIDENCE = 3 * _MIN_EVIDENCE


def _touches_ascii_letter(text: str, i: int) -> bool:
    return ((i > 0 and text[i - 1].isascii() and text[i - 1].isalpha())
            or (i + 1 < len(text) and text[i + 1].isascii() and text[i + 1].isalpha()))


def _plausible_cjk(text: str, encoding: str, codec: str) -> bool:
    """False when the decoded "CJK" text is really Western text read wrongly:
    too many characters built on an ASCII trail byte, or characters glued inside
    ASCII words ('I뭢 covering' is 'I’m covering' read as CP949)."""
    chars = [(i, c) for i, c in enumerate(text) if ord(c) > 127]
    if not chars:
        return False
    ascii_trailed = set()
    for i, c in chars:
        try:
            encoded = c.encode(codec)
        except UnicodeEncodeError:
            continue
        if len(encoded) == 2 and 0x40 <= encoded[1] <= 0x7E:
            ascii_trailed.add(i)
    if len(ascii_trailed) / len(chars) > _MAX_ASCII_TRAIL_SHARE[encoding]:
        return False
    letters = [i for i, c in chars if c.isalpha()]
    if not letters:
        return True
    glued = [i for i in letters if _touches_ascii_letter(text, i)]
    if len(letters) >= _STRONG_CJK_EVIDENCE:
        # Plenty of CJK text: a character glued to an English word ('John이',
        # '用LINE联系') is only suspicious when one of its bytes is ASCII. Western
        # text read wrongly ('I’m' -> 'I뭢') always builds its "characters" from a
        # high byte plus the ASCII letter after it, and those "characters" are
        # rare ones. A real Hangul / GB2312 character next to Latin letters uses
        # two high bytes; Big5 (whose trail byte may be ASCII) gives common Hanzi.
        glued = [i for i in glued if i in ascii_trailed and text[i] not in _COMMON_HANZI]
    return len(glued) / len(letters) <= _MAX_MIXED_SHARE


def _detect_cjk(data: bytes) -> Optional[tuple[str, int]]:
    """(encoding, letter count) for Shift-JIS / EUC-KR / GB18030 / Big5: the bytes
    must decode strictly AND give enough of the letters that language is really
    written with. Decoding alone proves nothing: these code pages accept almost
    any byte pair."""
    text = _strict(data, "cp932")
    if text is not None:
        letters = _foreign_letters(text)
        hiragana = sum(1 for c in letters if "぀" <= c <= "ゟ")
        if (len(letters) >= _MIN_EVIDENCE and hiragana / len(letters) >= _HIRAGANA_RATIO
                and _plausible_cjk(text, "shift_jis", "cp932")):
            return "shift_jis", len(letters)

    text = _strict(data, "cp949")
    if text is not None:
        letters = _foreign_letters(text)
        hangul = sum(1 for c in letters if "가" <= c <= "힣")
        if (len(letters) >= _MIN_EVIDENCE and hangul / len(letters) >= _HANGUL_RATIO
                and _plausible_cjk(text, "euc-kr", "cp949")):
            return "euc-kr", len(letters)

    best, best_score, best_count = None, 0.0, 0
    for encoding, codec in (("gb18030", "gb18030"), ("big5", "cp950")):
        text = _strict(data, codec)
        if text is None:
            continue
        hanzi = [c for c in _foreign_letters(text) if "一" <= c <= "鿿"]
        if len(hanzi) < _MIN_EVIDENCE or not _plausible_cjk(text, encoding, codec):
            continue
        score = sum(1 for c in hanzi if c in _COMMON_HANZI) / len(hanzi)
        if score > best_score:
            best, best_score, best_count = encoding, score, len(hanzi)
    return (best, best_count) if best and best_score >= _COMMON_HANZI_RATIO else None


# ── single-byte scripts other than Latin ──────────────────────────────────────
#
# Arabic, Cyrillic, Greek, Hebrew and Thai code pages all put their letters on
# the same high bytes, so each of them decodes the others into "valid" letters.
# What tells them apart is how often each letter occurs: the right code page
# gives the letter frequencies of a real language, a wrong one a scramble.

def _freq(table: str) -> dict[str, float]:
    """'а8 б1.6 ...' -> {letter: probability}."""
    pairs = [(item[0], float(item[1:])) for item in table.split()]
    total = sum(weight for _, weight in pairs)
    return {letter: weight / total for letter, weight in pairs}


_RUSSIAN = _freq(
    "о10.97 е8.45 а8.01 и7.35 н6.7 т6.26 с5.47 р4.73 в4.54 л4.4 к3.49 м3.21 д2.98 п2.81 "
    "у2.62 я2.01 ы1.9 ь1.74 г1.7 з1.65 б1.59 ч1.44 й1.21 х0.97 ж0.94 ш0.73 ю0.64 ц0.48 "
    "щ0.36 э0.32 ф0.26 ъ0.04 ё0.1 і0.3 ї0.1 є0.1 ґ0.02 ў0.05")
_GREEK = _freq(
    "α10.5 ο8.5 ι7.5 ε7 τ7.8 ν6.5 σ3.8 ς2.7 η4 υ3.5 ρ4.3 π4 κ4 μ3.3 λ2.7 γ1.8 δ1.7 θ1.3 "
    "χ1.1 ω1.3 φ0.8 β0.7 ξ0.4 ψ0.15 ζ0.4 ά2 έ1.5 ί1.8 ό1.8 ή1.2 ύ1 ώ0.6 ϊ0.1 ϋ0.05 ΐ0.02")
_HEBREW = _freq(
    "י11 ו10 ה8.5 ל7 א6.3 מ5 ם2.8 ת5 ב4.8 נ4 ן1.8 ר5.6 ש4.2 ע3.3 כ2.8 ך0.9 ד2.8 ק2 "
    "ח2.3 פ1.4 ף0.3 ס1 ג1.2 ז0.8 ט1.2 צ1 ץ0.2")
_ARABIC = _freq(
    "ا11 أ1.5 إ0.7 آ0.3 ل11 ي7 م6 و6 ن6 ه4.5 ة2.5 ر4.5 ت4.5 ب4 ع3.5 ك3 د3 ف3 س2.5 ق2.5 "
    "ح2 ج1.5 ى1.5 ش1 ص1 خ1 ط0.8 ء0.3 ئ0.3 ؤ0.2 ذ0.8 ز0.5 ث0.5 غ0.4 ض0.4 ظ0.2 ـ0.1 "
    # Persian and Urdu letters Windows-1256 also holds
    "پ0.4 چ0.4 ژ0.05 گ0.6 ک1 ٹ0.05 ڈ0.05 ڑ0.05 ں0.1 ھ0.1 ہ0.2 ے0.2")
# Urdu as Windows-1256 writes it: that code page has no Farsi yeh (U+06CC), so
# the Arabic yeh stands in for it; heh goal (ہ), yeh barree (ے), keheh (ک),
# noon ghunna (ں) and do-chashmi heh (ھ) are among the most frequent letters.
_URDU = _freq(
    "ا10 ي8.5 ک4.8 ے4.5 ہ4.4 ر4.6 ن4.5 و4.3 م3.8 ت3 ب2.5 ل2.5 س2.6 ں1.6 د1.6 ھ1.8 "
    "ج1.4 گ1.4 پ1 ئ0.8 آ0.7 ع0.8 چ0.6 ٹ0.6 ق0.6 ف0.6 ش0.6 ح0.6 خ0.5 ز0.5 ڈ0.4 ڑ0.4 "
    "ه0.8 ص0.3 ط0.2 غ0.2 ء0.2 ض0.1 ظ0.1 ذ0.1 ث0.1 ى0.1 ة0.05 ؤ0.05 أ0.05 إ0.02 ژ0.02")
_THAI = _freq(
    "า8.5 น6.5 ร5.5 อ5.3 ก5 เ4.8 ง4.5 ม4 ่4.2 ย3.4 ล3.3 ว3 ด3 ั3.4 ท2.7 ส2.5 ไ2.3 ้2.8 "
    "ี2.5 ิ2.6 บ2.2 ค2.3 ะ2 ห2 ต2 ป1.6 พ1.4 ุ1.3 จ1.3 แ1.4 ข1.1 ็1 ู0.8 ใ0.9 โ0.7 ช1 "
    "ื1 ์0.7 ำ0.7 ผ0.5 ถ0.5 ญ0.3 ษ0.3 ซ0.4 ศ0.4 ณ0.4 ภ0.3 ฟ0.3 ฝ0.1 ธ0.4 ฉ0.1 ฐ0.1 "
    "ฒ0.05 ฮ0.1 ๆ0.3 ฤ0.1 ฎ0.05 ฏ0.05 ฑ0.05 ฬ0.05 ๊0.2 ๋0.1 ฆ0.02 ฌ0.02")

def _entropy(table: dict[str, float]) -> float:
    return sum(p * math.log(p) for p in table.values())


# (encoding id, letter frequencies, script has upper/lower case, combining marks
# are letters). Only Thai writes vowels as combining marks; Arabic harakat
# (tashkeel) and Hebrew points are optional decoration and are left out.
_SCRIPT_CANDIDATES = [
    ("cp1256", _ARABIC, False, False),
    ("cp1256", _URDU, False, False),
    ("cp1251", _RUSSIAN, True, False),
    ("koi8_r", _RUSSIAN, True, False),
    ("cp1253", _GREEK, True, False),
    ("cp1255", _HEBREW, False, False),
    ("cp874", _THAI, False, True),
]

_UNSEEN_LETTER_P = 0.0005
# Mean ln(p) per letter, relative to the language's own average (its entropy):
# real text scores about 0, letters scrambled by a wrong code page far below.
_MIN_LOG_LIKELIHOOD = -0.5
# A clear winner is needed: two code pages scoring alike would be a guess.
_MIN_LEAD = 0.3
_MIN_KNOWN_SHARE = 0.85
_MAX_UPPERCASE_SHARE = 0.5
_MAX_CASE_FLIPS = 0.03
_MAX_MIXED_SHARE = 0.2


def _letters_and_marks(text: str, marks: bool) -> list[int]:
    """Positions of non-ASCII letters, plus combining marks when `marks` (Thai
    vowels are marks; Arabic harakat are not letters and are skipped)."""
    return [i for i, c in enumerate(text)
            if ord(c) > 127 and (c.isalpha() or (marks and unicodedata.category(c).startswith("M")))]


def _script_score(text: str, table: dict[str, float], bicameral: bool,
                  marks: bool = False) -> Optional[tuple[float, int]]:
    """(mean ln p relative to the language's entropy, letter count) of the text as
    this language; None when it cannot be."""
    positions = _letters_and_marks(text, marks)
    if not positions:
        return None
    letters = [text[i] for i in positions]
    known = [c for c in letters if c.lower() in table]
    # The language's own letters must make up the text...
    if len(known) / len(letters) < _MIN_KNOWN_SHARE:
        return None
    # ...not glued to Latin letters, which happens when Western text ('très')
    # is read with a non-Latin code page ('trиs')...
    mixed = sum(1 for i in positions if _touches_ascii_letter(text, i))
    if mixed / len(positions) > _MAX_MIXED_SHARE:
        return None
    # ...and mostly lower case, with capitals only at the start of words: a wrong
    # code page mixes the cases ('αΗδ'), KOI8-R read as Windows-1251 swaps them.
    if bicameral:
        if sum(1 for c in known if c.isupper()) / len(known) > _MAX_UPPERCASE_SHARE:
            return None
        flips = sum(1 for i in positions
                    if text[i].isupper() and i > 0 and text[i - 1].islower())
        if flips / len(positions) > _MAX_CASE_FLIPS:
            return None
    score = sum(math.log(table.get(c.lower(), _UNSEEN_LETTER_P)) for c in letters) / len(letters)
    return score - _entropy(table), len(letters)


def _detect_script(data: bytes) -> Optional[str]:
    sample = data[:_SAMPLE_BYTES]
    scores = []
    for encoding, table, bicameral, marks in _SCRIPT_CANDIDATES:
        text = _strict(sample, encoding)
        if text is None:
            continue
        result = _script_score(text, table, bicameral, marks)
        if result is not None:
            scores.append((result[0], result[1], encoding))
    if not scores:
        return None
    # One score per code page (Arabic and Urdu are both Windows-1256): the lead
    # is measured against the best OTHER code page.
    best_per_page: dict[str, tuple] = {}
    for item in scores:
        if item[2] not in best_per_page or item > best_per_page[item[2]]:
            best_per_page[item[2]] = item
    scores = sorted(best_per_page.values(), reverse=True)
    best, count, encoding = scores[0]
    lead = best - scores[1][0] if len(scores) > 1 else math.inf
    if count >= _MIN_EVIDENCE and best >= _MIN_LOG_LIKELIHOOD and lead >= _MIN_LEAD:
        return encoding
    return None


# ── Latin code pages ──────────────────────────────────────────────────────────
#
# Western (1252), Central European (1250) and Turkish (1254) share most bytes.
# Read with the wrong one, a text shows letters its languages never use, or
# symbols wedged inside words ('mo¿e' for Polish 'może').

def _with_upper(letters: str) -> frozenset[str]:
    return frozenset(letters + letters.upper())


_LATIN_LETTERS = {
    # French, German, Spanish, Portuguese, Italian, Dutch, Nordic. 'ð', 'þ' and
    # 'ý' are left out on purpose: in subtitles they are Turkish read as 1252.
    "cp1252": _with_upper("àáâãäåæçèéêëìíîïñòóôõöøùúûüœšž") | {"ß", "ÿ", "ª", "º"},
    # Polish, Czech, Slovak, Hungarian, Croatian, Slovenian, Romanian
    "cp1250": _with_upper("ąćęłńóśźżčďěňřšťůžýáéíúôäĺľŕöőüűđâăîşţ") | {"ß"},
    "cp1254": _with_upper("çğöşüâîû") | {"ı", "İ"},
}
# On a tie Turkish goes before Central European: the bytes both accept are
# Turkish 'ı ş ğ' but Czech 'ý', Romanian 'ţ' and Croatian 'đ' together.
_LATIN_ORDER = ("cp1252", "cp1254", "cp1250")
# Typographic punctuation that may sit between two letters: "l’école", "I…I",
# "Wait…what?", "word“hope”means", "one•two", "rock–paper". Every one of these
# is the same byte in Windows-1250, -1252 and -1254, so it never stands for a
# letter of another Latin code page. Other symbols between letters ('mo¿e',
# 'by³o') are letters of a different code page and stay problems.
_IN_WORD_PUNCTUATION = frozenset("’‘“”…•·–—­ ™")
# Above this share of high-byte letters standing in words without any ASCII
# letter, the text is not a Latin language ('Да' read as 1252 is 'Äà').
_MAX_ALL_HIGH_WORDS = 0.5


def _latin_problems(text: str, allowed: frozenset[str]) -> int:
    """Characters that cannot appear in a text of these languages."""
    problems = 0
    last = len(text) - 1
    for i, c in enumerate(text):
        if ord(c) <= 127:
            continue
        if c.isalpha():
            problems += c not in allowed
        elif (0 < i < last and text[i - 1].isalpha() and text[i + 1].isalpha()
              and c not in _IN_WORD_PUNCTUATION):
            problems += 1
    return problems


# ── Vietnamese (Windows-1258) ─────────────────────────────────────────────────
#
# Windows-1258 writes most Vietnamese tones as a combining mark after the vowel
# ('Vie' + U+0323 + 't'). Read as Windows-1250 the same bytes are 'ě ň Ţ Ň Ě',
# all valid Central European letters, so Vietnamese has to be checked first.

_VIETNAMESE_TONES = frozenset("̣̀́̃̉")
_VIETNAMESE_VOWELS = _with_upper("aăâeêioôơuưy")
# Letters Windows-1258 holds precomposed that Vietnamese uses
_VIETNAMESE_LETTERS = _with_upper("àáâăèéêíóôơùúưđ")
# Letters only Vietnamese uses (bytes that are ã õ ð ý in Windows-1252)
_VIETNAMESE_ONLY = _with_upper("ăơưđ")
_MIN_TONES_AFTER_VOWEL_SHARE = 0.8


def _detect_vietnamese(data: bytes) -> Optional[str]:
    """'cp1258' for clear Vietnamese, ENCODING_UNCERTAIN when the bytes look like
    Vietnamese tones but not clearly enough, None when they are not Vietnamese."""
    text = _strict(data[:_SAMPLE_BYTES], "cp1258")
    if text is None:
        return None
    tones = [i for i, c in enumerate(text) if c in _VIETNAMESE_TONES]
    after_vowel = sum(1 for i in tones if i > 0 and text[i - 1] in _VIETNAMESE_VOWELS)
    specific = sum(1 for c in text if c in _VIETNAMESE_ONLY)
    if (after_vowel < 3 or after_vowel / len(tones) < _MIN_TONES_AFTER_VOWEL_SHARE
            or not specific):
        return None
    without_tones = "".join(c for c in text if c not in _VIETNAMESE_TONES)
    if (after_vowel >= _MIN_EVIDENCE and specific >= 3
            and _latin_problems(without_tones, _VIETNAMESE_LETTERS) == 0):
        return "cp1258"
    return ENCODING_UNCERTAIN


def _all_high_word_share(text: str) -> float:
    """Share of the non-ASCII letters standing in words with no ASCII letter."""
    total = alone = 0
    for word in text.split():
        high = sum(1 for c in word if ord(c) > 127 and c.isalpha())
        if not high:
            continue
        total += high
        if not any(c.isascii() and c.isalpha() for c in word):
            alone += high
    return alone / total if total else 0.0


def _detect_latin(data: bytes) -> Optional[str]:
    sample = data[:_SAMPLE_BYTES]
    western = _strict(sample, "cp1252")
    if western is not None and _all_high_word_share(western) > _MAX_ALL_HIGH_WORDS:
        return None
    problems = {}
    for encoding in _LATIN_ORDER:
        text = western if encoding == "cp1252" else _strict(sample, encoding)
        if text is not None:
            problems[encoding] = _latin_problems(text, _LATIN_LETTERS[encoding])
    if not problems:
        return None
    best = min(problems, key=problems.get)                # first minimum = preferred
    return best if problems[best] == 0 else None


def detect_encoding(data: bytes) -> Optional[str]:
    """Encoding id of subtitle bytes, ENCODING_UNCERTAIN when no code page clearly
    fits, or None when the data is not text.

    Order: BOM -> UTF-16 without BOM -> strict UTF-8 -> CJK code pages ->
    Arabic / Cyrillic / Greek / Hebrew / Thai -> Vietnamese -> Western, Central
    European, Turkish. A CJK guess backed by only a few characters gives way to a
    Western code page that reads the file without a single odd character.
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
    if cjk is not None:
        encoding, count = cjk
        if count < _STRONG_CJK_EVIDENCE:
            latin = _detect_latin(data)
            if latin:
                return latin
        return encoding
    return (_detect_script(data) or _detect_vietnamese(data) or _detect_latin(data)
            or ENCODING_UNCERTAIN)


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
    (UTF-8, any BOM), when the file is not text, or when the encoding is uncertain."""
    encoding = detect_file_encoding(path)
    if encoding is None:
        logger.warning(f"{Path(path).name} does not look like a text file; no encoding passed.")
        return None
    if encoding == ENCODING_UNCERTAIN:
        logger.warning(f"{Path(path).name}: {UNCERTAIN_HINT}. No encoding was passed to mkvmerge.")
        return None
    if encoding in ("utf-8", "utf-8-sig", "utf-16", "utf-32"):   # mkvmerge reads BOMs itself
        return None
    return encoding


class UnknownCharsetError(ValueError):
    """An encoding name that is not in the table of names mkvmerge accepts."""


_ALIASES = {"shift-jis": "shift_jis", "sjis": "shift_jis", "euckr": "euc-kr"}


def resolve_charset(path: Path, setting: str) -> Optional[str]:
    """Turn the user's setting ('auto', '' or an explicit charset) into the value
    for mkvmerge's --sub-charset, or None when no flag is needed.

    Only names from the known table are ever returned; an explicit name outside
    it raises UnknownCharsetError instead of reaching mkvmerge.
    """
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
    name = mkvmerge_charset(_ALIASES.get(key, setting))
    if name is None:
        raise UnknownCharsetError(f"Unknown subtitle encoding '{setting}'.")
    return name


def is_known_charset(setting: Optional[str]) -> bool:
    """True for 'auto', '' and every name resolve_charset() accepts."""
    key = (setting or "").strip().lower().replace("_", "-")
    if key in ("", CHARSET_AUTO, "utf8", "utf16") or key in _ALIASES:
        return True
    return mkvmerge_charset(setting) is not None
