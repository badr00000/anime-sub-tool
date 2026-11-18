import pytest

from core import subtitle_file as sf

SRT = (
    "1\r\n00:00:01,000 --> 00:00:02,000\r\nHello\r\n\r\n"
    "2\r\n00:00:03,000 --> 00:00:04,500\r\n<i>World</i>\r\n\r\n"
    "3\r\n00:01:00,250 --> 00:01:02,000\r\nBye\r\n"
)

ASS = (
    "[Script Info]\nTitle: x\n\n[V4+ Styles]\nFormat: Name, Fontname\nStyle: Default,Arial\n\n"
    "[Events]\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\\an8}Hello, world\n"
    "Comment: 0,0:00:03.00,0:00:04.00,Default,,0,0,0,,note\n"
    "Dialogue: 0,0:00:05.50,0:00:07.25,Default,,0,0,0,,Second\\Nline\n"
)


def write(path, text, encoding="utf-8"):
    path.write_bytes(text.encode(encoding))
    return path


def test_srt_load_and_shift(tmp_path):
    sub = sf.load(write(tmp_path / "a.srt", SRT))
    assert [(c.start_ms, c.end_ms, c.text) for c in sub.cues] == [
        (1000, 2000, "Hello"), (3000, 4500, "World"), (60250, 62000, "Bye")]
    shifted = sf.shifted_text(sub, 1500)
    assert "00:00:02,500 --> 00:00:03,500" in shifted
    assert "00:01:01,750 --> 00:01:03,500" in shifted
    assert "<i>World</i>" in shifted                 # text untouched
    assert sf.shifted_text(sub, 0) == sub.text


def test_crlf_and_lf_line_endings_are_kept(tmp_path):
    crlf = sf.load(write(tmp_path / "crlf.srt", SRT))
    out = sf.save_shifted(crlf, 500)
    data = out.read_bytes()
    assert data.startswith(b"\xef\xbb\xbf")
    assert data.count(b"\r\n") == SRT.count("\r\n")
    assert b"\n" not in data.replace(b"\r\n", b"")

    lf = sf.load(write(tmp_path / "lf.srt", SRT.replace("\r\n", "\n")))
    assert b"\r" not in sf.save_shifted(lf, 500).read_bytes()


def test_ass_shift_keeps_everything_but_times(tmp_path):
    sub = sf.load(write(tmp_path / "a.ass", ASS))
    assert [(c.start_ms, c.end_ms, c.text) for c in sub.cues] == [
        (1000, 2000, "Hello, world"), (5500, 7250, "Second\nline")]
    shifted = sf.shifted_text(sub, -500)
    assert "Dialogue: 0,0:00:00.50,0:00:01.50,Default,,0,0,0,,{\\an8}Hello, world" in shifted
    assert "Comment: 0,0:00:02.50,0:00:03.50,Default,,0,0,0,,note" in shifted
    assert "Dialogue: 0,0:00:05.00,0:00:06.75,Default,,0,0,0,,Second\\Nline" in shifted
    assert shifted.startswith("[Script Info]\nTitle: x\n")


def test_negative_shift_clamps_and_counts(tmp_path):
    sub = sf.load(write(tmp_path / "a.srt", SRT))
    assert sf.count_clamped(sub, 500) == 0
    assert sf.count_clamped(sub, -1000) == 0          # first cue lands exactly on 0
    assert sf.count_clamped(sub, -1001) == 1
    assert sf.count_clamped(sub, -3500) == 2
    assert sf.count_clamped(sub, -3_600_000) == 3
    shifted = sf.shifted_text(sub, -3500)
    assert "00:00:00,000 --> 00:00:00,000" in shifted   # clamped, never negative
    assert "-" not in shifted.replace("-->", "")


def test_nested_tags_are_stripped_completely(tmp_path):
    text = ("1\n00:00:01,000 --> 00:00:02,000\n"
            "<<b>img src=\"file:///C:/secret.png\"<i>>visible <b>bold</b>\n")
    sub = sf.load(write(tmp_path / "evil.srt", text))
    assert "<" not in sub.cues[0].text and ">" not in sub.cues[0].text
    assert sub.cues[0].text == "visible bold"


def test_default_output_and_same_file_refusal(tmp_path):
    src = write(tmp_path / "Show - 01.srt", SRT)
    sub = sf.load(src)
    assert sf.default_output_path(src).name == "Show - 01.synced.srt"

    with pytest.raises(sf.SameFileError):
        sf.save_shifted(sub, 1000, src)
    assert src.read_bytes() == SRT.encode()            # untouched

    out = sf.save_shifted(sub, 1000)
    assert out.name == "Show - 01.synced.srt"

    # Re-syncing the synced copy would overwrite its own source
    synced = sf.load(out)
    before = out.read_bytes()
    with pytest.raises(sf.SameFileError):
        sf.save_shifted(synced, 1000)
    assert out.read_bytes() == before
    sf.save_shifted(synced, 1000, force=True)
    assert out.read_bytes() != before
    assert "00:00:03,000 --> 00:00:04,000" in out.read_text(encoding="utf-8-sig")


@pytest.mark.parametrize("codec, encoding", [
    ("utf-16-le", "utf-16-le"), ("utf-16", "utf-16"), ("cp1256", "cp1256"), ("utf-8-sig", "utf-8-sig"),
])
def test_load_other_encodings(tmp_path, codec, encoding):
    text = SRT.replace("Hello", "مرحبا بكم في هذا العالم الجميل").replace("Bye", "إلى اللقاء يا صديقي")
    sub = sf.load(write(tmp_path / "ar.srt", text, codec))
    assert sub.encoding == encoding
    assert len(sub.cues) == 3
    assert sub.cues[0].text == "مرحبا بكم في هذا العالم الجميل"
    assert not sub.text.startswith("\ufeff")


def test_empty_and_binary_files(tmp_path):
    assert sf.load(write(tmp_path / "empty.srt", "")).cues == []
    assert sf.load(write(tmp_path / "nocue.srt", "just some text\n")).cues == []
    junk = tmp_path / "junk.srt"
    junk.write_bytes(bytes(range(256)) * 20)
    with pytest.raises(ValueError):
        sf.load(junk)
    with pytest.raises(ValueError):
        sf.load(write(tmp_path / "a.vtt", "WEBVTT\n"))


# ── R2-08: times beyond what the format can hold ──────────────────────────────

def test_ass_times_past_9_59_59_are_refused(tmp_path):
    sub = sf.load(write(tmp_path / "a.ass", ASS))
    assert "9:00:01.00" in sf.shifted_text(sub, 9 * 3_600_000)         # still fits
    with pytest.raises(ValueError, match="9:59:59.99"):
        sf.shifted_text(sub, 10 * 3_600_000)
    with pytest.raises(ValueError):
        sf.save_shifted(sub, 10 * 3_600_000, tmp_path / "out.ass")
    assert not (tmp_path / "out.ass").exists()


def test_srt_times_past_99_hours_are_refused(tmp_path):
    sub = sf.load(write(tmp_path / "a.srt", SRT))
    with pytest.raises(ValueError, match="99:59:59,999"):
        sf.shifted_text(sub, 100 * 3_600_000)


# ── R2-03: reading with a chosen encoding ─────────────────────────────────────

def test_load_with_an_explicit_encoding(tmp_path):
    from core.subtitles import ENCODING_UNCERTAIN
    path = write(tmp_path / "ru.srt", SRT.replace("Hello", "Да"), "cp1251")
    guessed = sf.load(path)
    assert guessed.encoding == ENCODING_UNCERTAIN and "Да" not in guessed.cues[0].text
    chosen = sf.load(path, "cp1251")
    assert chosen.encoding == "cp1251" and chosen.cues[0].text == "Да"
    with pytest.raises(ValueError):
        sf.load(path, "klingon-8")
