"""Round 3 charset findings: Western text must never be read as CJK (R3A-01) or
flagged uncertain for ordinary typography (R3A-02); Arabic with tashkeel and
Persian are Windows-1256 (R3A-03); Vietnamese Windows-1258 is never silently read
as Windows-1250 (R3A-06). Every file here is a realistic 10-40 cue subtitle."""

import random
import shutil
import subprocess
import unicodedata
from pathlib import Path

import pytest

from conftest import MKVMERGE
from core.subtitles import (
    CHARSET_CHOICES, ENCODING_UNCERTAIN, _IN_WORD_PUNCTUATION, detect_charset, detect_encoding,
    mkvmerge_charset, resolve_charset,
)

CJK = {"shift_jis", "euc-kr", "gb18030", "big5"}


def srt(lines, cues=None) -> str:
    """An SRT of `cues` cues (default: one per line) cycling through `lines`."""
    cues = cues or len(lines)
    out = []
    for i in range(cues):
        start = 1000 + i * 2500
        out.append(f"{i + 1}\r\n{_t(start)} --> {_t(start + 2000)}\r\n{lines[i % len(lines)]}\r\n\r\n")
    return "".join(out)


def ass(lines, cues=None) -> str:
    cues = cues or len(lines)
    head = ("[Script Info]\r\nScriptType: v4.00+\r\n\r\n[V4+ Styles]\r\n"
            "Format: Name, Fontname, Fontsize\r\nStyle: Default,Arial,20\r\n\r\n[Events]\r\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\r\n")
    body = []
    for i in range(cues):
        s = 1 + i * 2.5
        body.append(f"Dialogue: 0,0:00:{int(s):02d}.{int(s * 100) % 100:02d},"
                    f"0:00:{int(s) + 2:02d}.00,Default,,0,0,0,,{lines[i % len(lines)]}\r\n")
    return head + "".join(body)


def _t(ms: int) -> str:
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ── English Windows-1252 ──────────────────────────────────────────────────────

ENGLISH = [
    "I'm covering for you, don't worry.", "We'll be fine. It's not that far.",
    "You're late again!", "That's what I've been saying all along.",
    "Where did you put the map?", "Nobody knows where they went.",
    "Let's go before it gets dark.", "Can you hear me? Answer me!",
    "I didn't see anything, I swear.", "She's waiting for us at the gate.",
    "This is the last train tonight.", "Hold on, I need to think.",
    "They've already left the village.", "We have to protect them.",
    "He said he'd come back tomorrow.", "Thank you for everything.",
    "What are you doing here?", "Come on, hurry up!",
    "Isn't that the captain's sword?", "I won't let you down this time.",
]


def curly(lines, limit=None):
    """Straight apostrophes -> ’, at most `limit` of them."""
    out, used = [], 0
    for line in lines:
        new = ""
        for c in line:
            if c == "'" and (limit is None or used < limit):
                new += "’"
                used += 1
            else:
                new += c
        out.append(new)
    return out


def plain(lines):
    return [l.replace("'", "") for l in lines]


def apostrophes_only(n):
    """Exactly n curly apostrophes, nothing else non-ASCII."""
    base = plain(ENGLISH)
    contractions = ["I’m sure.", "Don’t go.", "It’s fine.", "We’ll see.", "You’re right.",
                    "That’s it.", "I’ve got it.", "He’s here.", "They’re gone.", "Can’t stop."]
    lines = [f"{base[i % len(base)]} {contractions[i % len(contractions)]}" for i in range(n)]
    lines += base[: max(0, 10 - n)]
    return lines


ENGLISH_VARIANTS = {
    "apostrophes_8": srt(apostrophes_only(8), 12),
    "apostrophes_20": srt(apostrophes_only(20)),
    "apostrophes_50": srt(apostrophes_only(25), 40) + srt(apostrophes_only(10)),
    "apostrophes_in_all_lines": srt(curly(ENGLISH), 30),
    "curly_double_quotes": srt(curly(ENGLISH) + ["He said “stop” and left.", "“Run!” she shouted.",
                                                  "The word “hope” means nothing here."], 25),
    "quotes_glued": srt(curly(ENGLISH) + ["The word“hope”means nothing.", "Call it“luck”if you want."] * 3),
    "ellipsis_glued": srt(curly(ENGLISH) + ["I…I don’t know.", "Wait…what?", "You…you’re alive?",
                                             "Maybe…maybe not."] * 2),
    "ellipsis_spaced": srt(curly(ENGLISH) + ["Wait … what?", "Well … I guess so.", "And then …"]),
    "en_dash": srt(curly(ENGLISH) + ["Pages 10–20 are missing.", "It was a win–win.",
                                      "Tokyo – Osaka, last train."]),
    "em_dash": srt(curly(ENGLISH) + ["I was going to—", "rock—paper—scissors!",
                                      "He—no, she—did it."] * 2),
    "accented_words": srt(curly(ENGLISH) + ["Meet me at the café.", "Send me your résumé.",
                                             "Don’t be so naïve.", "Déjà vu again.",
                                             "My fiancée is waiting.", "Señor, por favor."]),
    "symbols": srt(curly(ENGLISH) + ["Add ½ cup of sugar.", "It’s 30° outside.", "© 2024 Studio",
                                      "Brand™ quality", "It costs £10.", "Only €5!", "A 3 × 4 grid."]),
    "nbsp": srt([l.replace(" ", "\xa0", 1) for l in curly(ENGLISH)], 20),
    "bullets": srt(curly(ENGLISH) + ["one•two•three", "• Item one", "• Item two"]),
    "mixed_everything": srt(curly(ENGLISH) + ["“I…I can’t,” she said—quietly.", "Café ½ price – today!",
                                               "He’s six feet tall… or so.", "© Studio™ “Hope”"], 40),
    "ass_apostrophes": ass(curly(ENGLISH), 25),
    "ass_tags_and_quotes": ass(["{\\i1}" + l + "{\\i0}" for l in curly(ENGLISH)]
                               + ["{\\an8}“Episode 5”", "I…I’m{\\b1}sorry{\\b0}."], 30),
    "single_quotes": srt(curly(ENGLISH) + ["‘Run,’ he said.", "She called it ‘home’."]),
    "leading_apostrophes": srt(curly(ENGLISH) + ["’Cause I said so.", "Wait ’til morning.",
                                                  "Rock ’n’ roll!"]),
    "shouting": srt([l.upper() for l in curly(ENGLISH)], 20),
    "possessives": srt([f"{n}’s {o} is here." for n in ("Naruto", "Sasuke", "Kakashi", "Sakura")
                        for o in ("sword", "bag", "map")]),
    "short_ten_cues": srt(apostrophes_only(10)[:10]),
    "long_forty_cues": srt(curly(ENGLISH), 40),
    "ellipsis_only": srt(plain(ENGLISH)[:12] + ["Hmm…", "Well…", "So…", "And…then?"], 16),
    "money_and_degrees": srt(plain(ENGLISH)[:10] + ["£10 or €12?", "It’s 25°C.", "×2 bonus!",
                                                     "½ off"], 14),
    "soft_hyphen_and_tm": srt(curly(ENGLISH) + ["extra\xadordinary", "Studio™s best"]),
    "lots_of_curly_everything": srt(curly(ENGLISH) * 2 + ["“Don’t…”", "“Won’t—”"], 40),
}


def test_at_least_25_english_variants():
    assert len(ENGLISH_VARIANTS) >= 25


@pytest.mark.parametrize("name", sorted(ENGLISH_VARIANTS))
def test_english_cp1252_variants(name):
    text = ENGLISH_VARIANTS[name]
    assert 10 <= text.count("-->") or "Dialogue:" in text
    data = text.encode("cp1252")
    assert detect_encoding(data) == "cp1252", name


def test_apostrophe_english_is_not_korean_any_more():
    """The R3A-01 reproduction: 'I’m covering' must not become 'I뭢 covering'."""
    data = srt(apostrophes_only(20)).encode("cp1252")
    assert data.decode("cp949")          # the bytes really are valid CP949
    assert detect_encoding(data) == "cp1252"
    text = data.decode("cp1252")
    assert "I’m sure." in text


GERMAN_VARIANTS = {
    "ellipsis": ["Ich…ich weiß nicht.", "Was…was ist passiert?", "Schön, dass du da bist.",
                 "Wir müssen über die Größe reden.", "Das wäre schön, tschüß!"],
    "quotes": ["Er sagte „Halt“ und ging.", "Das Wort“Hoffnung”bedeutet viel.",
               "Hör auf – sofort!", "Grüße an alle."],
}


@pytest.mark.parametrize("name", sorted(GERMAN_VARIANTS))
def test_german_cp1252_typography(name):
    data = srt(GERMAN_VARIANTS[name], 20).encode("cp1252")
    assert detect_encoding(data) == "cp1252"


def test_in_word_punctuation_is_the_same_byte_in_every_latin_page():
    for c in _IN_WORD_PUNCTUATION:
        encoded = {c.encode(cp) for cp in ("cp1250", "cp1252", "cp1254")}
        assert len(encoded) == 1, c


WORDS = ("the we you they captain village sword train night gate map home friend "
         "listen run stop wait never always maybe really again tomorrow tonight").split()
CONTRACTIONS = ["I’m", "don’t", "it’s", "you’re", "we’ll", "can’t", "won’t", "he’s", "they’ve",
                "isn’t", "Naruto’s", "she’d", "’cause", "y’know"]
DECOR = ["“{w}”", "{w}…", "…{w}", "{w}—", "{w} – {w}", "{w}•{w}", "‘{w}’", "{w}…{w}",
         "“{w}”{w}", "{w}\xa0{w}"]
EXTRA = ["café", "résumé", "naïve", "déjà", "fiancée", "señor", "Pokémon", "Zoë", "½", "30°",
         "©", "™", "£5", "€10", "3×4", "±2", "§4", "¼", "smörgåsbord", "Ångström", "Øre"]


def random_english(rng: random.Random) -> bytes:
    lines = []
    for _ in range(rng.randint(10, 40)):
        words = []
        for _ in range(rng.randint(3, 10)):
            r = rng.random()
            if r < 0.25:
                words.append(rng.choice(CONTRACTIONS))
            elif r < 0.35:
                words.append(rng.choice(DECOR).format(w=rng.choice(WORDS)))
            elif r < 0.40:
                words.append(rng.choice(EXTRA))
            else:
                words.append(rng.choice(WORDS))
        line = " ".join(words)
        line = line[0].upper() + line[1:] + rng.choice([".", "!", "?", "…", "!?", ""])
        if rng.random() < 0.1:
            line = line.upper()
        if rng.random() < 0.1:
            line = "<i>" + line + "</i>"
        lines.append(line)
    text = srt(lines) if rng.random() < 0.7 else ass(lines)
    return text.encode("cp1252")


def english_rates(count=300, seed=20241119):
    rng = random.Random(seed)
    results = [detect_encoding(random_english(rng)) for _ in range(count)]
    cjk = sum(1 for r in results if r in CJK)
    uncertain = sum(1 for r in results if r == ENCODING_UNCERTAIN)
    wrong = sum(1 for r in results if r not in ("cp1252", ENCODING_UNCERTAIN))
    return count, cjk, uncertain, wrong


def test_random_english_files_are_never_cjk_and_rarely_uncertain():
    count, cjk, uncertain, wrong = english_rates()
    assert count >= 200
    assert cjk == 0
    assert uncertain / count <= 0.02, uncertain
    assert wrong == 0, wrong


def test_utf8_english_never_gets_a_charset(tmp_path):
    for name, text in ENGLISH_VARIANTS.items():
        data = text.encode("utf-8")
        assert detect_encoding(data) == "utf-8", name
        path = tmp_path / f"{name}.srt"
        path.write_bytes(data)
        assert detect_charset(path) is None
        assert resolve_charset(path, "auto") is None


# ── Arabic / Persian Windows-1256 ─────────────────────────────────────────────

ARABIC_PLAIN = ["مرحبا بك في هذا العالم", "لا أعرف ماذا أقول لك الآن", "هذا هو المكان الذي كنا فيه",
                "إلى أين أنت ذاهب يا صديقي؟", "شكرا لك على كل شيء", "يجب أن نذهب قبل حلول الظلام",
                "هل تسمعني؟ أجبني!", "لن أخذلك هذه المرة", "انتظر لحظة، أحتاج إلى التفكير",
                "لقد غادروا القرية بالفعل"]
ARABIC_LIGHT = ["مرحبًا بك في هذا العالَم", "لا أعرفُ ماذا أقول لك الآن", "هذا هو المكانُ الذي كنّا فيه",
                "إلى أين أنتَ ذاهب يا صديقي؟", "شكرًا لك على كلّ شيء", "يجب أن نذهبَ قبل حلول الظلام",
                "هل تسمعني؟ أجبني!", "لن أخذلكَ هذه المرّة", "انتظر لحظةً، أحتاج إلى التفكير",
                "لقد غادروا القريةَ بالفعل"]
ARABIC_FULL = ["مَرْحَبًا بِكَ فِي هَذَا الْعَالَمِ", "لَا أَعْرِفُ مَاذَا أَقُولُ لَكَ الْآنَ",
               "هَذَا هُوَ الْمَكَانُ الَّذِي كُنَّا فِيهِ", "إِلَى أَيْنَ أَنْتَ ذَاهِبٌ يَا صَدِيقِي؟",
               "شُكْرًا لَكَ عَلَى كُلِّ شَيْءٍ", "يَجِبُ أَنْ نَذْهَبَ قَبْلَ حُلُولِ الظَّلَامِ",
               "هَلْ تَسْمَعُنِي؟ أَجِبْنِي!", "لَنْ أَخْذُلَكَ هَذِهِ الْمَرَّةَ",
               "انْتَظِرْ لَحْظَةً، أَحْتَاجُ إِلَى التَّفْكِيرِ", "لَقَدْ غَادَرُوا الْقَرْيَةَ بِالْفِعْلِ"]
PERSIAN = ["سلام، حال شما چطور است؟", "من نمی‌دانم چه بگویم", "ما باید همین حالا برویم",
           "کجا داری می‌روی؟", "این کتاب مال پدرم است", "گربه روی دیوار نشسته بود",
           "ژاله در باغ گل می‌کارد", "پسر کوچک به مدرسه رفت", "چرا اینقدر دیر کردی؟",
           "فردا دوباره همدیگر را می‌بینیم"]


def cp1256(text: str) -> bytes:
    # Windows-1256 has no Farsi yeh (U+06CC): Persian files use the Arabic one
    return text.replace("\u06cc", "\u064a").encode("cp1256")


@pytest.mark.parametrize("lines", [ARABIC_PLAIN, ARABIC_LIGHT, ARABIC_FULL, PERSIAN],
                         ids=["plain", "light_tashkeel", "full_tashkeel", "persian"])
def test_arabic_script_cp1256(lines, tmp_path):
    data = cp1256(srt(lines, 20))
    assert detect_encoding(data) == "cp1256"
    path = tmp_path / "ar.srt"
    path.write_bytes(data)
    assert resolve_charset(path, "auto") == "CP1256"


def test_full_tashkeel_has_marks_and_decodes_exactly():
    text = srt(ARABIC_FULL, 20)
    assert sum(1 for c in text if unicodedata.category(c) == "Mn") > 100
    data = cp1256(text)
    assert data.decode(detect_encoding(data)) == text


# ── every earlier language case still holds (realistic file sizes) ────────────

LANGUAGES = {
    "french": (["Bonjour, ça va très bien.", "Où est-il allé ? Je ne sais pas.",
                "C'est déjà fini, même si tu étais là.", "Peut-être à l'école, près du château.",
                "Ça m'est égal, à bientôt !"], "cp1252", "cp1252"),
    "spanish": (["¿Cómo estás? Mañana iré a la montaña.", "Él está aquí, sí. ¿Qué pasó después?",
                 "Adiós, señor. Será difícil, quizás más tarde."], "cp1252", "cp1252"),
    "german": (["Schön, daß du da bist.", "Wir müssen über die Größe der Tür reden.",
                "Ich hätte gern Käse und Brötchen."], "cp1252", "cp1252"),
    "portuguese": (["Não sei o que dizer.", "Ação e emoção, não é?", "Você está aqui, irmão."],
                   "cp1252", "cp1252"),
    "russian": (["Привет, как дела?", "Я не знаю, что сказать.", "Это было очень давно, но я всё помню.",
                 "Мы должны идти дальше, пока не стемнело."], "cp1251", "cp1251"),
    "ukrainian": (["Привіт, як справи?", "Я не знаю, що сказати.", "Ми повинні йти далі."],
                  "cp1251", "cp1251"),
    "russian_koi8": (["Привет, как дела?", "Я не знаю, что сказать.",
                      "Это было очень давно, но я всё помню."], "koi8_r", "koi8_r"),
    "greek": (["Γεια σου, τι κάνεις;", "Δεν ξέρω τι να πω.", "Πρέπει να φύγουμε τώρα, ευχαριστώ."],
              "cp1253", "cp1253"),
    "hebrew": (["שלום, מה שלומך?", "אני לא יודע מה להגיד.", "אנחנו צריכים ללכת עכשיו, תודה."],
               "cp1255", "cp1255"),
    "thai": (["สวัสดีครับ คุณสบายดีไหม", "ผมไม่รู้ว่าจะพูดอะไรดี", "เราจะไปที่ไหนกันตอนนี้"],
             "cp874", "cp874"),
    "polish": (["Cześć, jak się masz?", "Nie wiem, co powiedzieć.", "Możemy iść już teraz, dziękuję."],
               "cp1250", "cp1250"),
    "czech": (["Dobrý den, jak se máte?", "Nevím, co říct.", "Musíme jít hned teď, děkuji."],
              "cp1250", "cp1250"),
    "turkish": (["Merhaba, nasılsın?", "Ne diyeceğimi bilmiyorum.",
                 "Şimdi gitmemiz gerekiyor, teşekkür ederim."], "cp1254", "cp1254"),
    "japanese": (["こんにちは、元気ですか？", "私は学生です。", "それは何ですか？わかりません。",
                  "カタカナとひらがなを使います。"], "shift_jis", "shift_jis"),
    "chinese_gbk": (["你好，你是谁？", "我不知道你在说什么。", "我们现在要去哪里？", "这是一个很好的地方。"],
                    "gbk", "gb18030"),
    "chinese_big5": (["你好，你是誰？", "我不知道你在說什麼。", "我們現在要去哪裡？", "這是一個很好的地方。"],
                     "big5", "big5"),
    "korean": (["안녕하세요, 잘 지내세요?", "저는 학생입니다.", "그것은 무엇입니까? 모르겠습니다.",
                "감사합니다. 내일 다시 만나요."], "euc-kr", "euc-kr"),
    "utf16_bom": (ARABIC_PLAIN, "utf-16", "utf-16"),
    "utf16_le": (ARABIC_PLAIN, "utf-16-le", "utf-16-le"),
    "utf16_be": (ENGLISH, "utf-16-be", "utf-16-be"),
}


@pytest.mark.parametrize("name", sorted(LANGUAGES))
@pytest.mark.parametrize("cues", [10, 40])
def test_previous_languages_still_detected(name, cues):
    lines, codec, expected = LANGUAGES[name]
    assert detect_encoding(srt(lines, cues).encode(codec)) == expected


# ── Vietnamese Windows-1258 (R3A-06) ──────────────────────────────────────────

_TONES = "\u0300\u0301\u0303\u0309\u0323"


def to_cp1258(text: str) -> bytes:
    """Encode as Windows does: base letter (with ^, breve or horn) + tone mark."""
    out = []
    for ch in unicodedata.normalize("NFC", text):
        try:
            out.append(ch.encode("cp1258"))
            continue
        except UnicodeEncodeError:
            pass
        parts = unicodedata.normalize("NFD", ch)
        base = unicodedata.normalize("NFC", "".join(c for c in parts if c not in _TONES))
        out.append((base + "".join(c for c in parts if c in _TONES)).encode("cp1258"))
    return b"".join(out)


VIETNAMESE = ["Xin chào, bạn có khỏe không?", "Tôi không biết phải nói gì.",
              "Chúng ta phải đi ngay bây giờ.", "Cảm ơn bạn rất nhiều.",
              "Đừng lo, mọi chuyện sẽ ổn thôi.", "Bạn đang làm gì ở đây vậy?",
              "Tiếng Việt rất đẹp.", "Hẹn gặp lại vào ngày mai."]


def test_vietnamese_cp1258_is_detected_not_cp1250(tmp_path):
    data = to_cp1258(srt(VIETNAMESE, 20))
    assert data.decode("cp1250")              # also valid Central European bytes
    assert detect_encoding(data) == "cp1258"
    path = tmp_path / "vi.srt"
    path.write_bytes(data)
    assert resolve_charset(path, "auto") == "CP1258"
    assert unicodedata.normalize("NFC", data.decode("cp1258")) == srt(VIETNAMESE, 20)


def test_little_vietnamese_is_uncertain_not_cp1250():
    data = to_cp1258(srt(["Cảm ơn", "Hello there", "Good night", "See you"], 10))
    assert detect_encoding(data) == ENCODING_UNCERTAIN


def test_cp1258_is_offered_and_known_to_mkvmerge():
    assert ("Windows-1258 (Vietnamese)", "cp1258") in CHARSET_CHOICES
    assert mkvmerge_charset("cp1258") == "CP1258"
    assert mkvmerge_charset("windows-1258") == "CP1258"


# ── real mkvmerge + mkvextract: the text inside the MKV is right ──────────────

MKVEXTRACT = Path(shutil.which("mkvextract") or r"C:\Program Files\MKVToolNix\mkvextract.exe")


@pytest.mark.mkvmerge
@pytest.mark.skipif(not MKVEXTRACT.is_file(), reason="mkvextract is not installed")
@pytest.mark.parametrize("name, text, data", [
    ("english_apostrophes", srt(apostrophes_only(20)), srt(apostrophes_only(20)).encode("cp1252")),
    ("arabic_full_tashkeel", srt(ARABIC_FULL, 20), cp1256(srt(ARABIC_FULL, 20))),
    ("vietnamese", unicodedata.normalize("NFD", srt(VIETNAMESE, 12)), to_cp1258(srt(VIETNAMESE, 12))),
])
def test_text_inside_the_mkv_is_correct(tmp_path, name, text, data):
    from conftest import make_wav
    from core.engine import ProcessingEngine
    from core.models import AppConfig, ProcessingOptions

    wav = make_wav(tmp_path / "a.wav", seconds=1)
    subprocess.run([str(MKVMERGE), "-q", "-o", str(tmp_path / "Show - 01.mkv"),
                    "--language", "0:jpn", str(wav)], check=True, capture_output=True, timeout=60)
    wav.unlink()
    (tmp_path / "Show - 01.srt").write_bytes(data)

    engine = ProcessingEngine(AppConfig())
    result = engine.process_batch(engine.scan_and_match(tmp_path), ProcessingOptions())
    assert result.successful == 1, [r.message for r in result.results]
    assert not any("uncertain" in w for r in result.results for w in r.warnings)

    out = tmp_path / "PROCESSED" / "Show - 01.mkv"
    extracted = tmp_path / "extracted.srt"
    subprocess.run([str(MKVEXTRACT), str(out), "tracks", f"1:{extracted}"],
                   check=True, capture_output=True, timeout=60)
    got = extracted.read_bytes().decode("utf-8-sig")
    expected_lines = [l for l in text.splitlines() if l and "-->" not in l and not l.isdigit()]
    got_nfc = unicodedata.normalize("NFC", got)
    for line in expected_lines:
        assert unicodedata.normalize("NFC", line) in got_nfc, line
    if name == "english_apostrophes":
        assert "I’m sure." in got and "\ubb22" not in got           # not 'I뭢'
