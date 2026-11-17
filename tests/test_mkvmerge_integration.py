"""End-to-end runs with the real bin/mkvmerge.exe (skipped when it is missing)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import MKVMERGE, ROOT, SRT_TEXT, make_wav, write_srt
from core.engine import ProcessingEngine
from core.mkvtools import MKVToolsWrapper, _path_arg, locate_mkvmerge
from core.models import AppConfig, ProcessingOptions, ProcessingStatus as S
from utils.validators import validate_mkvtoolnix

pytestmark = pytest.mark.mkvmerge

ARABIC_LINE_1 = "مرحبا بكم في هذا العالم الجميل"
ARABIC_LINE_2 = "إلى اللقاء يا صديقي العزيز"
ARABIC_SRT = SRT_TEXT.replace("Hello", ARABIC_LINE_1).replace("World", ARABIC_LINE_2)
JAPANESE_LINE = "こんにちは、元気ですか？ありがとうございます"
JAPANESE_SRT = SRT_TEXT.replace("Hello", JAPANESE_LINE).replace("World", "それは何ですか？わかりません")


def identify(path: Path) -> dict:
    out = subprocess.run([str(MKVMERGE), "-J", str(path)], capture_output=True,
                         text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def tracks(path: Path, kind: str) -> list[dict]:
    return [t for t in identify(path)["tracks"] if t["type"] == kind]


def make_episode(path: Path) -> Path:
    """A tiny Matroska file: one Japanese audio track and one English subtitle."""
    wav = make_wav(path.with_name(path.stem + ".src.wav"))
    srt = write_srt(path.with_name(path.stem + ".src.srt"))
    subprocess.run([str(MKVMERGE), "-q", "-o", str(path),
                    "--language", "0:jpn", str(wav),
                    "--language", "0:eng", "--track-name", "0:English", str(srt)],
                   check=True, capture_output=True)
    wav.unlink()
    srt.unlink()
    return path


@pytest.fixture
def engine():
    return ProcessingEngine(AppConfig())


def test_bundled_mkvmerge_is_found_and_valid():
    assert locate_mkvmerge("") == MKVMERGE
    assert locate_mkvmerge(r"Z:\no\such\folder") == MKVMERGE      # bad setting -> bundled copy
    tools = MKVToolsWrapper("")
    ok, message = tools.validate_installation()
    assert ok and message.startswith("mkvmerge v")
    assert validate_mkvtoolnix(tools).startswith("mkvmerge v")


def test_custom_folder_is_used_when_it_has_mkvmerge(tmp_path):
    fake = tmp_path / "mkvmerge.exe"
    fake.write_bytes(b"not a program")
    tools = MKVToolsWrapper(str(tmp_path))
    assert tools.mkvmerge_path == fake
    ok, message = tools.validate_installation()
    assert not ok
    assert "mkvmerge" in message and str(fake) in message      # says what and where
    with pytest.raises(ValueError, match="mkvmerge"):
        validate_mkvtoolnix(tools)
    info = tools.identify(str(tmp_path / "x.mkv"))
    assert "could not be started" in info.error and str(fake) in info.error
    result = tools.merge(str(tmp_path / "x.mkv"), str(tmp_path / "o.mkv"))
    assert result.status == S.FAILED and str(fake) in result.message


def test_path_arguments_are_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in ("@options.json", "-o", "--help", "plain.mkv"):
        arg = _path_arg(name)
        assert Path(arg).is_absolute() and not arg.startswith(("@", "-"))


def test_identify_reports_errors(tmp_path):
    tools = MKVToolsWrapper("")
    missing = tools.identify(str(tmp_path / "missing.mkv"))
    assert missing.error and "missing.mkv" in missing.error and not missing.tracks
    text = tmp_path / "notes.mkv"
    text.write_text("this is not a video")
    assert tools.identify(str(text)).error


def test_arabic_cp1256_is_converted_and_offset_applied(tmp_path, engine):
    make_episode(tmp_path / "Show - 01.mkv")
    write_srt(tmp_path / "Show - 01.srt", ARABIC_SRT, "cp1256")
    source_before = (tmp_path / "Show - 01.mkv").read_bytes()

    scan = engine.scan_and_match(tmp_path)
    assert scan.matches[0].subtitle.encoding == "Windows-1256 (Arabic)"
    options = ProcessingOptions(subtitle_offset_ms=2000)
    result = engine.process_batch(scan, options)
    assert (result.successful, result.failed, result.skipped) == (1, 0, 0)

    out = tmp_path / "PROCESSED" / "Show - 01.mkv"
    assert (tmp_path / "Show - 01.mkv").read_bytes() == source_before     # original untouched
    assert not list(out.parent.glob("*.partial"))

    subs = tracks(out, "subtitles")
    assert len(subs) == 1                                   # the English one was removed
    props = subs[0]["properties"]
    assert props["language"] == "ara" and props["track_name"] == "Arabic"
    assert props["default_track"] is True
    # First line starts at 1.000 s in the file; +2 s offset -> 3.000 s
    assert abs(props["minimum_timestamp"] - 3_000_000_000) < 1_000_000    # within 1 ms
    assert [t["properties"]["language"] for t in tracks(out, "audio")] == ["jpn"]

    data = out.read_bytes()
    assert ARABIC_LINE_1.encode("utf-8") in data            # stored as UTF-8
    assert ARABIC_LINE_1.encode("cp1256") not in data


@pytest.mark.parametrize("codec, text, needle", [
    ("utf-16-le", ARABIC_SRT, ARABIC_LINE_1),
    ("utf-16", ARABIC_SRT, ARABIC_LINE_1),
    ("utf-8-sig", ARABIC_SRT, ARABIC_LINE_1),
    ("shift_jis", JAPANESE_SRT, JAPANESE_LINE),
    ("cp1252", SRT_TEXT.replace("Hello", "Ça va très bien, déjà fini à l'école"),
     "Ça va très bien, déjà fini à l'école"),
])
def test_other_encodings_reach_the_mkv_as_utf8(tmp_path, engine, codec, text, needle):
    make_episode(tmp_path / "Show - 01.mkv")
    write_srt(tmp_path / "Show - 01.srt", text, codec)
    result = engine.process_batch(engine.scan_and_match(tmp_path), ProcessingOptions())
    assert result.successful == 1, [r.message for r in result.results]
    assert needle.encode("utf-8") in (tmp_path / "PROCESSED" / "Show - 01.mkv").read_bytes()
    assert [p.name for p in (tmp_path / "PROCESSED").iterdir()] == ["Show - 01.mkv"]


def test_keep_original_subs_and_no_offset(tmp_path, engine):
    make_episode(tmp_path / "Show - 01.mkv")
    write_srt(tmp_path / "Show - 01.srt")
    options = ProcessingOptions(remove_existing_subs=False, subtitle_language="fre",
                                subtitle_name="Français")
    assert engine.process_batch(engine.scan_and_match(tmp_path), options).successful == 1
    subs = tracks(tmp_path / "PROCESSED" / "Show - 01.mkv", "subtitles")
    assert [s["properties"]["language"] for s in subs] == ["eng", "fre"]
    assert subs[1]["properties"]["track_name"] == "Français"
    assert abs(subs[1]["properties"]["minimum_timestamp"] - 1_000_000_000) < 1_000_000


def test_at_sign_filename_in_relative_folder(tmp_path, monkeypatch, engine):
    """'@name' must be merged as a file, never read by mkvmerge as an option file."""
    make_episode(tmp_path / "ep.mkv").rename(tmp_path / "@Show - 01.mkv")
    # If '@Show - 01.srt' were taken as an option file, its JSON would attach secret.txt
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET-CONTENT")
    write_srt(tmp_path / "@Show - 01.srt")
    (tmp_path / "@trap.json").write_text(json.dumps(["--attach-file", str(secret)]))

    monkeypatch.chdir(tmp_path)
    scan = engine.scan_and_match(".")
    assert scan.folder_path.is_absolute()
    result = engine.process_batch(scan, ProcessingOptions())
    assert result.successful == 1, [r.message for r in result.results]

    out = tmp_path / "PROCESSED" / "@Show - 01.mkv"
    info = identify(out)
    assert info.get("attachments", []) == []
    assert b"TOP-SECRET-CONTENT" not in out.read_bytes()
    assert len([t for t in info["tracks"] if t["type"] == "subtitles"]) == 1

    # The wrapper itself is safe too when handed bare relative names
    direct = MKVToolsWrapper("").merge("@Show - 01.mkv", "direct.mkv", subtitle_path="@Show - 01.srt")
    assert direct.status == S.COMPLETED
    assert identify(tmp_path / "direct.mkv").get("attachments", []) == []


def test_cli_process_relative_folder_with_bundled_mkvmerge(tmp_path, isolated_home):
    """`main.py process .` works without a system MKVToolNix and with '@' names."""
    make_episode(tmp_path / "ep.mkv").rename(tmp_path / "@Show - 01.mkv")
    write_srt(tmp_path / "@Show - 01.srt")
    env = dict(os.environ, USERPROFILE=str(isolated_home), HOME=str(isolated_home), PATH="")
    env["SystemRoot"] = os.environ.get("SystemRoot", r"C:\Windows")
    run = subprocess.run([sys.executable, str(ROOT / "main.py"), "process", ".", "--yes"],
                         cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8")
    assert run.returncode == 0, run.stdout + run.stderr
    assert "Succeeded: 1" in run.stdout
    out = tmp_path / "PROCESSED" / "@Show - 01.mkv"
    assert len(tracks(out, "subtitles")) == 1
    log = isolated_home / ".anime-sub-tool" / "logs" / "anime-sub-tool.log"
    assert log.stat().st_size > 0 and "Running mkvmerge" in log.read_text(encoding="utf-8")


def test_mp4_named_input_gives_mkv_output(tmp_path, engine):
    make_episode(tmp_path / "ep.mkv").rename(tmp_path / "Show - 02.mp4")
    write_srt(tmp_path / "Show - 02.srt")
    result = engine.process_batch(engine.scan_and_match(tmp_path), ProcessingOptions())
    assert result.successful == 1
    assert [p.name for p in (tmp_path / "PROCESSED").iterdir()] == ["Show - 02.mkv"]
    assert identify(tmp_path / "PROCESSED" / "Show - 02.mkv")["container"]["type"] == "Matroska"


def test_skip_then_overwrite_existing_output(tmp_path, engine):
    make_episode(tmp_path / "Show - 01.mkv")
    write_srt(tmp_path / "Show - 01.srt")
    scan = engine.scan_and_match(tmp_path)
    assert engine.process_batch(scan, ProcessingOptions()).successful == 1
    out = tmp_path / "PROCESSED" / "Show - 01.mkv"
    first = out.stat().st_mtime_ns

    again = engine.process_batch(scan, ProcessingOptions())
    assert (again.successful, again.skipped) == (0, 1) and out.stat().st_mtime_ns == first

    forced = engine.process_batch(scan, ProcessingOptions(overwrite_existing=True, subtitle_name="Second"))
    assert forced.successful == 1
    assert tracks(out, "subtitles")[0]["properties"]["track_name"] == "Second"


def test_empty_subtitle_and_broken_video_fail(tmp_path, engine):
    make_episode(tmp_path / "Show - 01.mkv")
    (tmp_path / "Show - 01.srt").write_bytes(b"")
    (tmp_path / "Show - 02.mkv").write_text("not a video at all")
    write_srt(tmp_path / "Show - 02.srt")
    result = engine.process_batch(engine.scan_and_match(tmp_path), ProcessingOptions())
    assert (result.successful, result.failed) == (0, 2)
    assert "no subtitle lines" in result.results[0].message
    assert "Show - 02.mkv" in result.results[1].message
    out_dir = tmp_path / "PROCESSED"
    assert not out_dir.exists() or not list(out_dir.iterdir())


def test_same_folder_output_survives_a_second_run(tmp_path, engine):
    make_episode(tmp_path / "Show - 01.mkv")
    write_srt(tmp_path / "Show - 01.srt")
    options = ProcessingOptions(create_output_folder=False, overwrite_existing=True)
    assert engine.process_batch(engine.scan_and_match(tmp_path), options).successful == 1
    out = tmp_path / "Show - 01 [AnimeSubTool].mkv"
    assert len(tracks(out, "subtitles")) == 1

    rescan = engine.scan_and_match(tmp_path)
    assert [m.video.filename for m in rescan.matches] == ["Show - 01.mkv"]
    assert engine.process_batch(rescan, options).successful == 1
    assert len(tracks(out, "subtitles")) == 1                       # still the good output
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "Show - 01 [AnimeSubTool].mkv", "Show - 01.mkv", "Show - 01.srt"]
