import random

import pytest

from core.subtitles import (
    CHARSET_CHOICES, ENCODING_UNCERTAIN, UnknownCharsetError, describe_encoding, detect_charset,
    detect_encoding, detect_file_encoding, is_known_charset, mkvmerge_charset, resolve_charset,
)


def srt(*lines: str) -> str:
    out = []
    for i, line in enumerate(lines, 1):
        out.append(f"{i}\r\n00:00:{i:02d},000 --> 00:00:{i:02d},900\r\n{line}\r\n\r\n")
    return "".join(out)


ARABIC = srt("مرحبا بك في هذا العالم", "لا أعرف ماذا أقول لك الآن", "هذا هو المكان الذي كنا فيه",
             "إلى أين أنت ذاهب يا صديقي؟", "شكرا لك على كل شيء")
MIXED = srt("{\\an8}Naruto: مرحبا يا Sasuke", "<i>Opening theme</i>", "لا أعرف ماذا أقول",
            "Hokage sama هذا هو المكان", "OK, let's go! هيا بنا إلى القرية")
FRENCH = srt("Bonjour, ça va très bien.", "Où est-il allé ? Je ne sais pas.",
             "C'est déjà fini, même si tu étais là.", "Peut-être à l'école, près du château.",
             "Ça m'est égal, à bientôt !")
GERMAN = srt("Schön, daß du da bist.", "Wir müssen über die Größe der Tür reden.",
             "Ich hätte gern Käse und Brötchen.", "Das wäre schön, tschüß!")
SPANISH = srt("¿Cómo estás? Mañana iré a la montaña.", "Él está aquí, sí. ¿Qué pasó después?",
              "Adiós, señor. Será difícil, quizás más tarde.")
JAPANESE = srt("こんにちは、元気ですか？", "私は学生です。", "それは何ですか？わかりません。",
               "ありがとうございました。", "カタカナとひらがなを使います。")
CHINESE = srt("你好，你是谁？", "我不知道你在说什么。", "我们现在要去哪里？", "这是一个很好的地方。",
              "谢谢你，我们明天再见。")
TRADITIONAL = srt("你好，你是誰？", "我不知道你在說什麼。", "我們現在要去哪裡？", "這是一個很好的地方。",
                  "謝謝你，我們明天再見。")
KOREAN = srt("안녕하세요, 잘 지내세요?", "저는 학생입니다.", "그것은 무엇입니까? 모르겠습니다.",
             "감사합니다. 내일 다시 만나요.")
RUSSIAN = srt("Привет, как дела?", "Я не знаю, что сказать.", "Это было очень давно, но я всё помню.")


@pytest.mark.parametrize("text, codec, expected", [
    (ARABIC, "utf-8", "utf-8"),
    (FRENCH, "utf-8", "utf-8"),
    (srt("plain ascii only"), "ascii", "utf-8"),
    (ARABIC, "utf-8-sig", "utf-8-sig"),
    (ARABIC, "utf-16", "utf-16"),            # with BOM
    (ARABIC, "utf-16-le", "utf-16-le"),      # no BOM
    (ARABIC, "utf-16-be", "utf-16-be"),
    (FRENCH, "utf-16-le", "utf-16-le"),
    (ARABIC, "cp1256", "cp1256"),
    (MIXED, "cp1256", "cp1256"),
    (FRENCH, "cp1252", "cp1252"),
    (GERMAN, "cp1252", "cp1252"),
    (SPANISH, "cp1252", "cp1252"),
    (JAPANESE, "shift_jis", "shift_jis"),
    (JAPANESE, "cp932", "shift_jis"),
    (CHINESE, "gb18030", "gb18030"),
    (CHINESE, "gbk", "gb18030"),
    (TRADITIONAL, "big5", "big5"),
    (KOREAN, "euc-kr", "euc-kr"),
    (RUSSIAN, "cp1251", "cp1251"),
])
def test_detect_encoding(text, codec, expected):
    assert detect_encoding(text.encode(codec)) == expected


def test_random_bytes_are_not_text():
    rng = random.Random(1234)
    for size in (64, 4096, 50_000):
        data = bytes(rng.randrange(256) for _ in range(size))
        assert detect_encoding(data) is None


def test_binary_file_gets_no_charset(tmp_path):
    path = tmp_path / "junk.srt"
    rng = random.Random(7)
    path.write_bytes(bytes(rng.randrange(256) for _ in range(8192)))
    assert detect_file_encoding(path) is None
    assert detect_charset(path) is None
    assert resolve_charset(path, "auto") is None


@pytest.mark.parametrize("text, codec, charset", [
    (ARABIC, "utf-8", None),
    (ARABIC, "utf-8-sig", None),
    (ARABIC, "utf-16", None),               # mkvmerge reads the BOM itself
    (ARABIC, "utf-16-le", "utf-16-le"),
    (ARABIC, "cp1256", "cp1256"),
    (MIXED, "cp1256", "cp1256"),
    (FRENCH, "cp1252", "cp1252"),
    (JAPANESE, "shift_jis", "shift_jis"),
])
def test_detect_charset(tmp_path, text, codec, charset):
    path = tmp_path / "sub.srt"
    path.write_bytes(text.encode(codec))
    assert detect_charset(path) == charset


def test_resolve_charset(tmp_path):
    sjis = tmp_path / "ja.srt"
    sjis.write_bytes(JAPANESE.encode("shift_jis"))
    assert resolve_charset(sjis, "auto") == "CP932"
    assert resolve_charset(sjis, "shift_jis") == "CP932"
    assert resolve_charset(sjis, "utf-8") is None
    assert resolve_charset(sjis, "") is None
    assert resolve_charset(sjis, "KOI8-R") == "KOI8-R"      # a known iconv name is passed through

    u16 = tmp_path / "u16.srt"
    u16.write_bytes(ARABIC.encode("utf-16-le"))
    assert resolve_charset(u16, "auto") == "UTF-16LE"
    assert resolve_charset(u16, "utf-16") == "UTF-16LE"

    vobsub = tmp_path / "x.idx"
    vobsub.write_bytes(ARABIC.encode("cp1256"))
    assert resolve_charset(vobsub, "auto") is None         # not a text subtitle


def test_encoding_choices_cover_the_supported_set():
    values = [value for _, value in CHARSET_CHOICES]
    assert values == ["auto", "utf-8", "cp1256", "cp1252", "cp1250", "cp1254", "cp1258", "cp1251",
                      "koi8_r", "cp1253", "cp1255", "cp874", "shift_jis", "gb18030",
                      "big5", "euc-kr", "utf-16"]
    assert mkvmerge_charset("euc-kr") == "CP949"
    assert mkvmerge_charset("iso8859_2") == "ISO-8859-2"
    # Every choice reaches mkvmerge under a name from the known table
    for value in values[2:]:
        assert mkvmerge_charset(value), value


# ── R2-03: no confident wrong guesses ──────────────────────────────────────────

THAI = srt("สวัสดีครับ คุณสบายดีไหม", "ผมไม่รู้ว่าจะพูดอะไรดี", "เราจะไปที่ไหนกันตอนนี้",
           "ขอบคุณมากครับ แล้วพบกันใหม่")
RUSSIAN_LONG = srt("Привет, как дела?", "Я не знаю, что сказать.",
                   "Это было очень давно, но я всё помню.", "Мы должны идти дальше, пока не стемнело.",
                   "Ты слышишь меня? Отвечай!", "Наруто, подожди меня!",
                   "Сегодня мы будем тренироваться весь день.", "Хорошо, учитель.") * 3
RUSSIAN_SHORT_3 = srt("Где ты был?", "Мы идём домой.", "Подожди меня здесь!")
POLISH = srt("Cześć, jak się masz?", "Nie wiem, co powiedzieć.", "Możemy iść już teraz, dziękuję.",
             "Gdzie jest ta łódź? Zaraz będę.")
CZECH = srt("Dobrý den, jak se máte?", "Nevím, co říct.", "Musíme jít hned teď, děkuji.",
            "Kde je ten člun? Hned tam budu.")
TURKISH = srt("Merhaba, nasılsın?", "Ne diyeceğimi bilmiyorum.",
              "Şimdi gitmemiz gerekiyor, teşekkür ederim.", "Bir şey değil, görüşürüz.")
GREEK = srt("Γεια σου, τι κάνεις;", "Δεν ξέρω τι να πω.", "Πρέπει να φύγουμε τώρα, ευχαριστώ.",
            "Πού είναι η βάρκα;")
HEBREW = srt("שלום, מה שלומך?", "אני לא יודע מה להגיד.", "אנחנו צריכים ללכת עכשיו, תודה.",
             "איפה הסירה?")
UKRAINIAN = srt("Привіт, як справи?", "Я не знаю, що сказати.", "Ми повинні йти далі.")
PORTUGUESE = srt("Não sei o que dizer.", "Ação e emoção, não é?", "Você está aqui, irmão.")


@pytest.mark.parametrize("text, codec, expected", [
    (THAI, "cp874", "cp874"),                       # was cp1256
    (RUSSIAN, "cp1251", "cp1251"),                  # 3 lines
    (RUSSIAN_SHORT_3, "cp1251", "cp1251"),          # 3 short lines (was cp1255)
    (RUSSIAN_LONG, "cp1251", "cp1251"),             # was mac_cyrillic, which mkvmerge rejects
    (UKRAINIAN, "cp1251", "cp1251"),
    (RUSSIAN, "koi8_r", "koi8_r"),
    (GREEK, "cp1253", "cp1253"),
    (HEBREW, "cp1255", "cp1255"),
    (POLISH, "cp1250", "cp1250"),                   # was cp1252
    (CZECH, "cp1250", "cp1250"),
    (TURKISH, "cp1254", "cp1254"),                  # was cp1252
    (PORTUGUESE, "cp1252", "cp1252"),
    # Too little text to tell: uncertain, never a confident wrong guess
    (srt("Да"), "cp1251", ENCODING_UNCERTAIN),      # was euc-kr
    (srt("你好"), "gb18030", ENCODING_UNCERTAIN),    # was euc-kr
    (srt("東京都庁"), "shift_jis", ENCODING_UNCERTAIN),  # was euc-kr
])
def test_detect_encoding_new_code_pages_and_uncertain(text, codec, expected):
    assert detect_encoding(text.encode(codec)) == expected


def test_uncertain_file_gets_no_charset_and_says_so(tmp_path):
    path = tmp_path / "ru.srt"
    path.write_bytes(srt("Да").encode("cp1251"))
    assert detect_file_encoding(path) == ENCODING_UNCERTAIN
    assert detect_charset(path) is None
    assert resolve_charset(path, "auto") is None             # no --sub-charset at all
    assert "Uncertain" in describe_encoding(ENCODING_UNCERTAIN)
    assert resolve_charset(path, "cp1251") == "CP1251"       # the user's pick is passed


@pytest.mark.parametrize("text, codec, iconv", [
    (RUSSIAN_LONG, "cp1251", "CP1251"), (RUSSIAN, "koi8_r", "KOI8-R"), (THAI, "cp874", "CP874"),
    (GREEK, "cp1253", "CP1253"), (HEBREW, "cp1255", "CP1255"), (POLISH, "cp1250", "CP1250"),
    (TURKISH, "cp1254", "CP1254"), (ARABIC, "cp1256", "CP1256"), (FRENCH, "cp1252", "CP1252"),
    (CHINESE, "gb18030", "GB18030"), (TRADITIONAL, "big5", "CP950"), (KOREAN, "euc-kr", "CP949"),
])
def test_auto_detection_only_hands_mkvmerge_known_names(tmp_path, text, codec, iconv):
    path = tmp_path / "sub.srt"
    path.write_bytes(text.encode(codec))
    assert resolve_charset(path, "auto") == iconv


def test_unknown_explicit_charset_is_refused(tmp_path):
    path = tmp_path / "sub.srt"
    path.write_bytes(ARABIC.encode("cp1256"))
    with pytest.raises(UnknownCharsetError):
        resolve_charset(path, "klingon-8")
    assert mkvmerge_charset("mac_cyrillic") == "MACCYRILLIC"   # a Python name, mapped
    assert mkvmerge_charset("klingon-8") is None
    assert mkvmerge_charset(ENCODING_UNCERTAIN) is None
    assert is_known_charset("windows-1251") and is_known_charset("auto")
    assert not is_known_charset("klingon-8")
