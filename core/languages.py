"""
Anime Subtitle Automation Tool — language list for dropdowns and track matching.

Codes are ISO 639-2/B, which is what mkvmerge writes and reports ("fre", "ger",
"chi"). Users and other tools often use the /T form ("fra", "deu", "zho") or the
2-letter form ("fr", "ja"); normalize() maps all of those to one code so a track
is found whichever form was used.
"""

from __future__ import annotations

# (code, English name) — the ones anime fans need most come first, then A–Z.
COMMON = [
    ("jpn", "Japanese"),
    ("eng", "English"),
    ("ara", "Arabic"),
    ("chi", "Chinese"),
    ("kor", "Korean"),
    ("spa", "Spanish"),
    ("por", "Portuguese"),
    ("fre", "French"),
    ("ger", "German"),
    ("ita", "Italian"),
    ("rus", "Russian"),
]

OTHERS = [
    ("alb", "Albanian"), ("bul", "Bulgarian"), ("cat", "Catalan"), ("hrv", "Croatian"),
    ("cze", "Czech"), ("dan", "Danish"), ("dut", "Dutch"), ("est", "Estonian"),
    ("fil", "Filipino"), ("fin", "Finnish"), ("gre", "Greek"), ("heb", "Hebrew"),
    ("hin", "Hindi"), ("hun", "Hungarian"), ("ind", "Indonesian"), ("kur", "Kurdish"),
    ("lav", "Latvian"), ("lit", "Lithuanian"), ("may", "Malay"), ("nor", "Norwegian"),
    ("per", "Persian"), ("pol", "Polish"), ("rum", "Romanian"), ("srp", "Serbian"),
    ("slo", "Slovak"), ("slv", "Slovenian"), ("swe", "Swedish"), ("tha", "Thai"),
    ("tur", "Turkish"), ("ukr", "Ukrainian"), ("urd", "Urdu"), ("vie", "Vietnamese"),
]

UNDETERMINED = ("und", "Undetermined / no language set")

LANGUAGES = COMMON + sorted(OTHERS, key=lambda x: x[1])
NAMES = {code: name for code, name in LANGUAGES + [UNDETERMINED]}

# Other spellings of the same language -> the mkvmerge (639-2/B) code
_ALIASES = {
    # ISO 639-2/T
    "fra": "fre", "deu": "ger", "zho": "chi", "nld": "dut", "fas": "per", "ces": "cze",
    "ron": "rum", "slk": "slo", "ell": "gre", "sqi": "alb", "msa": "may",
    # ISO 639-1 / BCP 47 primary tags
    "ja": "jpn", "jp": "jpn", "en": "eng", "ar": "ara", "zh": "chi", "ko": "kor",
    "es": "spa", "pt": "por", "fr": "fre", "de": "ger", "it": "ita", "ru": "rus",
    "sq": "alb", "bg": "bul", "ca": "cat", "hr": "hrv", "cs": "cze", "da": "dan",
    "nl": "dut", "et": "est", "fi": "fin", "el": "gre", "he": "heb", "hi": "hin",
    "hu": "hun", "id": "ind", "ku": "kur", "lv": "lav", "lt": "lit", "ms": "may",
    "no": "nor", "nb": "nor", "fa": "per", "pl": "pol", "ro": "rum", "sr": "srp",
    "sk": "slo", "sl": "slv", "sv": "swe", "th": "tha", "tr": "tur", "uk": "ukr",
    "ur": "urd", "vi": "vie", "tl": "fil", "fil": "fil",
}


# Arabic names, only used so people can search the dropdowns in Arabic
ARABIC_NAMES = {
    "jpn": "ياباني اليابانية", "eng": "انجليزي إنجليزي الإنجليزية", "ara": "عربي العربية",
    "chi": "صيني الصينية", "kor": "كوري الكورية", "spa": "اسباني إسباني الإسبانية",
    "por": "برتغالي البرتغالية", "fre": "فرنسي الفرنسية", "ger": "الماني ألماني الألمانية",
    "ita": "ايطالي إيطالي الإيطالية", "rus": "روسي الروسية", "alb": "ألباني الألبانية",
    "bul": "بلغاري البلغارية", "cat": "كتالوني الكتالونية", "hrv": "كرواتي الكرواتية",
    "cze": "تشيكي التشيكية", "dan": "دنماركي الدنماركية", "dut": "هولندي الهولندية",
    "est": "استوني الإستونية", "fil": "فلبيني الفلبينية", "fin": "فنلندي الفنلندية",
    "gre": "يوناني اليونانية", "heb": "عبري العبرية", "hin": "هندي الهندية",
    "hun": "مجري المجرية", "ind": "اندونيسي إندونيسي الإندونيسية", "kur": "كردي الكردية",
    "lav": "لاتفي اللاتفية", "lit": "ليتواني الليتوانية", "may": "ملايو ماليزي الملايوية",
    "nor": "نرويجي النرويجية", "per": "فارسي الفارسية", "pol": "بولندي البولندية",
    "rum": "روماني الرومانية", "srp": "صربي الصربية", "slo": "سلوفاكي السلوفاكية",
    "slv": "سلوفيني السلوفينية", "swe": "سويدي السويدية", "tha": "تايلاندي التايلاندية",
    "tur": "تركي التركية", "ukr": "اوكراني أوكراني الأوكرانية", "urd": "اردو أردو الأردية",
    "vie": "فيتنامي الفيتنامية", "und": "غير محدد بدون لغة",
}


def search_text(code: str) -> str:
    """Everything a user might type to find this language: name, codes, Arabic name."""
    code = normalize(code)
    aliases = [a for a, target in _ALIASES.items() if target == code]
    return " ".join([NAMES.get(code, ""), code, *aliases, ARABIC_NAMES.get(code, "")]).lower()


def normalize(code: str | None) -> str:
    """'JA', 'ja-JP', 'jpn' -> 'jpn';  'fra' -> 'fre';  '' / None -> ''."""
    if not code:
        return ""
    c = code.strip().lower().replace("_", "-").split("-")[0]
    return _ALIASES.get(c, c)


def same_language(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and normalize(a) == normalize(b)


def display(code: str) -> str:
    """'jpn' -> 'Japanese (jpn)'; unknown codes are shown as-is."""
    code = normalize(code)
    name = NAMES.get(code)
    return f"{name} ({code})" if name else code


def name_of(code: str) -> str:
    """'ara' -> 'Arabic' (used as the default track name)."""
    return NAMES.get(normalize(code), code)
