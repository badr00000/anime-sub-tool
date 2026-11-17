import random

import pytest

from core.subtitles import (
    CHARSET_CHOICES, detect_charset, detect_encoding, detect_file_encoding,
    mkvmerge_charset, resolve_charset,
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
    assert resolve_charset(sjis, "KOI8-R") == "KOI8-R"      # any iconv name is passed through

    u16 = tmp_path / "u16.srt"
    u16.write_bytes(ARABIC.encode("utf-16-le"))
    assert resolve_charset(u16, "auto") == "UTF-16LE"
    assert resolve_charset(u16, "utf-16") == "UTF-16LE"

    vobsub = tmp_path / "x.idx"
    vobsub.write_bytes(ARABIC.encode("cp1256"))
    assert resolve_charset(vobsub, "auto") is None         # not a text subtitle


def test_encoding_choices_cover_the_supported_set():
    values = [value for _, value in CHARSET_CHOICES]
    assert values == ["auto", "utf-8", "cp1256", "cp1252", "shift_jis", "gb18030",
                      "big5", "euc-kr", "utf-16"]
    assert mkvmerge_charset("euc-kr") == "CP949"
    assert mkvmerge_charset("iso8859_2") == "ISO-8859-2"
