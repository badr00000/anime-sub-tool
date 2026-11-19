"""Round 4 findings: pairs are chosen best-first, not in file order (R4-01); the
subtitle language in a name is read and preferred (R4-02); films with years and
release groups pair (R4-03); video names keep their last word (R4-04);
`--keep-subs all` keeps every subtitle (R4-05); Urdu Windows-1256 (R4-06); CJK
glued to English words (R4-07); pairing by hand in the Preview step."""

import random
import time
from pathlib import Path

import pytest
from click.testing import CliRunner
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QTableWidget

from conftest import MKVMERGE, SRT_TEXT, write_srt
from core.engine import ProcessingEngine
from core.matcher import extract_episode_info, match_files, numberless_title, subtitle_language_tag
from core.models import (
    AppConfig, BatchResult, FileInfo, MatchConfidence, ProcessingOptions, ProcessingResult,
    ProcessingStatus as S,
)
from core.subtitles import ENCODING_UNCERTAIN, detect_charset, detect_encoding


def info(name: str):
    return extract_episode_info(Path("C:/season") / name)


def pairs(videos, subs, language="ara"):
    matches, unmatched_v, unmatched_s = match_files(
        [info(v) for v in videos], [info(s) for s in subs], language)
    return ({m.video.filename: (m.subtitle.filename if m.subtitle else None) for m in matches},
            matches, unmatched_v, unmatched_s)


# ── R4-01: best pair first ────────────────────────────────────────────────────

@pytest.mark.parametrize("videos, subs, expected", [
    (["5 Centimeters per Second (2007).mkv", "Show - 05.mkv"], ["Show - 05.ar.srt"],
     {"5 Centimeters per Second (2007).mkv": None, "Show - 05.mkv": "Show - 05.ar.srt"}),
    (["[Group] Detective Conan Movie 26.mkv", "Detective Conan - 26.mkv"], ["Detective Conan - 26.srt"],
     {"[Group] Detective Conan Movie 26.mkv": None, "Detective Conan - 26.mkv": "Detective Conan - 26.srt"}),
    (["Bleach - 05.mkv", "Naruto - 05.mkv"], ["Naruto - 05.srt", "Bleach - 05.srt"],
     {"Bleach - 05.mkv": "Bleach - 05.srt", "Naruto - 05.mkv": "Naruto - 05.srt"}),
])
def test_best_pair_wins_whatever_the_file_order(videos, subs, expected):
    for v in (videos, list(reversed(videos))):
        for s in (subs, list(reversed(subs))):
            got, matches, unmatched_v, unmatched_s = pairs(v, s)
            assert got == expected
            assert [m.video.filename for m in matches] == v                # order kept
            assert sorted(x.filename for x in unmatched_v) == sorted(
                name for name, sub in expected.items() if sub is None)
            assert not unmatched_s


def test_a_lone_low_score_pair_still_pairs_but_is_flagged():
    got, matches, _, _ = pairs(["5 Centimeters per Second (2007).mkv"], ["Show - 05.ar.srt"])
    assert got["5 Centimeters per Second (2007).mkv"] == "Show - 05.ar.srt"
    assert matches[0].confidence == MatchConfidence.LOW


# ── R4-02: language tags ──────────────────────────────────────────────────────

@pytest.mark.parametrize("name, tag", [
    ("Show - 01.en.srt", "eng"), ("Show - 01.eng.srt", "eng"), ("Show - 01.ar.srt", "ara"),
    ("Show - 01.ara.ass", "ara"), ("Show - 01.ja.srt", "jpn"), ("Show - 01.jpn.srt", "jpn"),
    ("Show - 01.fra.srt", "fre"), ("Show - 01.pt-BR.srt", "por"), ("Show - 01.Arabic.srt", "ara"),
    ("Show - 01 (English).srt", "eng"), ("Show - 01 [ENG].srt", "eng"),
    ("Show - 01 (عربي).srt", "ara"), ("Show - 01 [Arabic].srt", "ara"),
    ("Show - 01 [Arabic Subs].srt", "ara"), ("Show - 01.en.synced.srt", "eng"),
    ("Show - 01.srt", ""), ("[Group] Show - 01 [1080p].srt", ""), ("Show - 01 [BD].srt", ""),
])
def test_language_tag_is_read_from_subtitle_names(name, tag):
    assert info(name).language == tag
    assert subtitle_language_tag(Path(name).stem) == tag


def test_video_names_get_no_language_tag():
    assert info("Show - 01 [ENG].mkv").language == ""


@pytest.mark.parametrize("subs", [
    ["Show - 01.srt", "Show - 01.en.srt"], ["Show - 01.en.srt", "Show - 01.srt"],
])
def test_untagged_beats_another_language(subs):
    got, matches, _, unmatched_s = pairs(["Show - 01.mkv"], subs, "ara")
    assert got == {"Show - 01.mkv": "Show - 01.srt"}
    assert matches[0].language_warning == "" and matches[0].subtitle_language == ""
    assert [s.filename for s in unmatched_s] == ["Show - 01.en.srt"]


@pytest.mark.parametrize("subs, wanted, chosen", [
    (["Show - 01 (English).srt", "Show - 01 (عربي).srt"], "ara", "Show - 01 (عربي).srt"),
    (["Show - 01 (عربي).srt", "Show - 01 (English).srt"], "eng", "Show - 01 (English).srt"),
    (["Show - 01.srt", "Show - 01.ar.srt"], "ara", "Show - 01.ar.srt"),    # wanted > untagged
    (["Show - 01.srt", "Show - 01.en.srt"], "eng", "Show - 01.en.srt"),
    (["Show - 01.ar.srt", "Show - 01.en.srt"], "ara", "Show - 01.ar.srt"),
    (["Show - 01.ar.srt", "Show - 01.en.srt"], "en", "Show - 01.en.srt"),  # any spelling
])
def test_wanted_language_wins(subs, wanted, chosen):
    got, matches, _, _ = pairs(["Show - 01.mkv"], subs, wanted)
    assert got == {"Show - 01.mkv": chosen}
    assert matches[0].language_warning == ""


def test_other_language_never_beats_untagged_even_with_a_better_title():
    # R5-05 narrowed this rule: it holds while the untagged title scores at least
    # 50 (another spelling of the same show); an unrelated show (< 50) now loses,
    # see test_round5.py::test_unrelated_untagged_show_loses_to_another_language
    got, matches, _, _ = pairs(["Show - 01.mkv"], ["Show - 01.en.srt", "[Fansub] The Show - 01.srt"])
    assert got == {"Show - 01.mkv": "[Fansub] The Show - 01.srt"}
    assert 50 <= matches[0].score < 80


def test_only_candidate_in_another_language_is_paired_with_a_warning():
    got, matches, _, _ = pairs(["Show - 01.mkv"], ["Show - 01.en.srt"], "ara")
    assert got == {"Show - 01.mkv": "Show - 01.en.srt"}
    assert matches[0].is_matched and matches[0].subtitle_language == "eng"
    assert matches[0].language_warning == "subtitle looks like English, track will be labelled Arabic"
    # no wanted language / undetermined: no preference and no warning
    for wanted in ("", "und"):
        assert pairs(["Show - 01.mkv"], ["Show - 01.en.srt"], wanted)[1][0].language_warning == ""


def test_scan_uses_the_given_language_or_the_settings_one(tmp_path):
    (tmp_path / "Show - 01.mkv").write_bytes(b"v")
    write_srt(tmp_path / "Show - 01.ar.srt")
    write_srt(tmp_path / "Show - 01.en.srt")
    engine = ProcessingEngine(AppConfig(subtitle_language="eng"))
    assert engine.scan_and_match(tmp_path).matches[0].subtitle.filename == "Show - 01.en.srt"
    assert engine.scan_and_match(tmp_path, "ara").matches[0].subtitle.filename == "Show - 01.ar.srt"
    # every text subtitle gets its encoding, not only the matched one
    scan = engine.scan_and_match(tmp_path, "ara")
    assert all(s.encoding for s in scan.subtitle_files)


class RecordingTools:
    def __init__(self):
        self.merged = []

    def identify(self, path, cancel_event=None):
        return FileInfo(filepath=Path(path))

    def merge(self, cancel_event=None, **kwargs):
        self.merged.append(kwargs)
        Path(kwargs["output_path"]).write_bytes(b"out")
        return ProcessingResult(status=S.COMPLETED)

    def terminate_all(self):
        pass


def test_the_arabic_file_is_merged_not_the_english_one(tmp_path):
    (tmp_path / "Show - 01.mkv").write_bytes(b"v")
    write_srt(tmp_path / "Show - 01.srt", SRT_TEXT.replace("Hello", "مرحبا بكم في هذا العالم"), "cp1256")
    write_srt(tmp_path / "Show - 01.en.srt")
    tools = RecordingTools()
    engine = ProcessingEngine(AppConfig(), mkv_tools=tools)
    scan = engine.scan_and_match(tmp_path)
    assert engine.process_batch(scan, ProcessingOptions()).successful == 1
    assert Path(tools.merged[0]["subtitle_path"]).name == "Show - 01.srt"


def test_cli_scan_shows_the_language_warning(tmp_path, monkeypatch):
    import cli.commands as commands
    monkeypatch.setattr(commands, "setup_logging", lambda **kw: None)
    (tmp_path / "Show - 01.mkv").write_bytes(b"v")
    write_srt(tmp_path / "Show - 01.en.srt")
    out = CliRunner().invoke(commands.cli, ["scan", str(tmp_path)]).output
    assert "subtitle looks like English, track will be labelled Arabic" in out


# ── R4-03 / R4-04: films ──────────────────────────────────────────────────────

@pytest.mark.parametrize("video, sub", [
    ("Suzume 2022 1080p BluRay x265.mkv", "Suzume.ar.srt"),
    ("Suzume.2022.1080p.BluRay.x265-GROUP.mkv", "Suzume.2022.ar.srt"),
    ("Suzume.2022.1080p.BluRay.x265-GROUP.mkv", "Suzume.ar.srt"),
    ("Suzume (2022) [1080p].mkv", "Suzume.2022.srt"),
    ("1917.mkv", "1917.ar.srt"),
    ("Spider-Man.mkv", "Spider-Man.ar.srt"),
    ("Tenki.no.Ko.mkv", "Tenki.no.Ko.ara.srt"),
    ("Tenki.no.Ko.mkv", "Tenki.no.Ko.srt"),
    ("Tenki.no.Ko.2019.1080p.BluRay.x264-GRP.mkv", "Tenki.no.Ko.ar.srt"),
])
def test_films_pair(video, sub):
    got, matches, unmatched_v, unmatched_s = pairs([video], [sub])
    assert got == {video: sub} and not unmatched_v and not unmatched_s
    assert matches[0].score == 100 and matches[0].language_warning == ""


def test_numberless_title_details():
    assert numberless_title(info("Suzume.2022.1080p.BluRay.x265-GROUP.mkv")) == "suzume"
    assert numberless_title(info("1917.mkv")) == "1917"                    # year-only title kept
    assert numberless_title(info("Tenki.no.Ko.mkv")) == "tenki no ko"      # R4-04
    assert numberless_title(info("Tenki.no.Ko.ara.srt")) == "tenki no ko"
    assert numberless_title(info("Spider-Man.mkv")) == "spider man"         # no release tag: no group
    # 'Ko' ending a subtitle name is part of the title for 'Tenki.no.Ko.mkv'
    _, matches, _, _ = pairs(["Tenki.no.Ko.mkv"], ["Tenki.no.Ko.srt"])
    assert matches[0].subtitle_language == ""


def test_different_films_still_do_not_pair():
    got, _, _, _ = pairs(["Suzume 2022 1080p.mkv"], ["Weathering With You 2019.ar.srt"])
    assert got == {"Suzume 2022 1080p.mkv": None}


# ── R4-05: --keep-subs all ────────────────────────────────────────────────────

@pytest.fixture
def cli(monkeypatch):
    import cli.commands as commands
    monkeypatch.setattr(commands, "setup_logging", lambda **kw: None)
    return commands


@pytest.mark.parametrize("args, remove, langs", [
    (["--keep-subs", "all"], False, []),
    (["--keep-subs", "ALL"], False, []),
    (["--keep-original-subs"], False, []),
    (["--keep-subs", "eng"], True, ["eng"]),
    (["--keep-subs", ""], True, []),
    ([], True, []),
])
def test_keep_subs_all_reaches_the_options(cli, tmp_path, monkeypatch, args, remove, langs):
    (tmp_path / "Show - 01.mkv").write_bytes(b"v")
    write_srt(tmp_path / "Show - 01.srt")
    seen = {}
    monkeypatch.setattr(cli, "validate_mkvtoolnix", lambda tools: "mkvmerge v100")
    monkeypatch.setattr(ProcessingEngine, "process_batch",
                        lambda self, scan, opts, *a: seen.setdefault("opts", opts) and BatchResult())
    result = CliRunner().invoke(cli.cli, ["process", str(tmp_path), "-y", *args])
    assert result.exit_code == 0, result.output
    assert seen["opts"].remove_existing_subs is remove
    assert seen["opts"].keep_sub_langs == langs


def test_keep_subs_all_is_documented(cli):
    help_text = " ".join(CliRunner().invoke(cli.cli, ["process", "--help"]).output.split())
    assert "'all' keeps every original subtitle" in help_text
    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
    assert "--keep-subs all" in readme and "3600" in readme
    assert "Fix a pairing by hand" in readme and "Suzume.2022.1080p.BluRay.x265-GROUP.mkv" in readme


@pytest.mark.mkvmerge
def test_keep_subs_all_keeps_the_original_subtitle_in_the_real_file(cli, tmp_path, monkeypatch):
    from test_mkvmerge_integration import make_episode, tracks
    make_episode(tmp_path / "Show - 01.mkv")          # Japanese audio + English subtitle
    write_srt(tmp_path / "Show - 01.srt", SRT_TEXT.replace("Hello", "مرحبا بكم في هذا العالم"))
    result = CliRunner().invoke(cli.cli, ["process", str(tmp_path), "-y", "--keep-subs", "all"])
    assert result.exit_code == 0, result.output
    subs = tracks(tmp_path / "PROCESSED" / "Show - 01.mkv", "subtitles")
    assert sorted(t["properties"]["language"] for t in subs) == ["ara", "eng"]

    result = CliRunner().invoke(cli.cli, ["process", str(tmp_path), "-y", "--overwrite"])
    assert result.exit_code == 0, result.output
    subs = tracks(tmp_path / "PROCESSED" / "Show - 01.mkv", "subtitles")
    assert [t["properties"]["language"] for t in subs] == ["ara"]    # default: originals removed


# ── R4-06: Urdu ───────────────────────────────────────────────────────────────

# Windows-1256 has no Farsi yeh (U+06CC) nor the Urdu full stop: Urdu files use
# the Arabic yeh and '.'
URDU = [line.replace("ی", "ي").replace("۔", ".") for line in [
    "آپ کیسے ہیں؟ میں ٹھیک ہوں۔", "یہ میری کتاب ہے۔", "ہم کل بازار جائیں گے۔",
    "کیا تم نے کھانا کھایا؟", "مجھے نہیں معلوم وہ کہاں گیا ہے۔", "اس نے کہا کہ وہ آئے گا۔",
    "ہمیں جلدی کرنی چاہیے۔", "یہ بہت اچھا ہے، شکریہ۔", "وہ میرا دوست ہے۔", "تمہارا نام کیا ہے؟",
    "اگر تم چاہو تو ہم ساتھ چلیں گے۔", "یہاں سے نکلو، جلدی کرو!",
]]


@pytest.mark.parametrize("cues", [10, 30])
def test_urdu_cp1256_is_detected(tmp_path, cues):
    from test_charset_round3 import ass, srt
    for text in (srt(URDU, cues), ass(URDU, cues)):
        data = text.encode("cp1256")
        assert detect_encoding(data) == "cp1256"
        path = tmp_path / "urdu.srt"
        path.write_bytes(data)
        assert detect_charset(path) == "cp1256"


# ── R4-07: CJK glued to English words ─────────────────────────────────────────

GLUED = {
    "euc-kr": ("cp949", ["John이 뭐래?", "iPhone을 줘.", "Sarah한테 가.", "Tokyo에 와.",
                         "Mike는 어디?", "Google에 물어봐.", "Kakao로 보내.", "Seoul역 앞.",
                         "Coffee를 줘.", "Netflix를 봐."]),
    "gb18030": ("gb18030", ["用LINE联系", "在Google找", "John说了", "打开iPhone", "去Starbucks吧",
                            "用Facebook吗", "Mary在哪", "发到WeChat", "看Netflix吧", "Tom回家了"]),
    "big5": ("cp950", ["用LINE聯繫", "在Google找", "John說了", "打開iPhone", "去Starbucks吧",
                       "用Facebook嗎", "Mary在哪", "發到WeChat", "看Netflix吧", "Tom回家了"]),
}


@pytest.mark.parametrize("encoding", sorted(GLUED))
@pytest.mark.parametrize("cues", [20, 40])
def test_cjk_glued_to_english_words_is_detected(encoding, cues):
    from test_charset_round3 import srt
    codec, lines = GLUED[encoding]
    assert detect_encoding(srt(lines, cues).encode(codec)) == encoding


def test_english_cp1252_is_still_never_cjk_nor_uncertain():
    from test_charset_round3 import CJK, apostrophes_only, english_rates, srt
    for seed in (20241119, 1, 2):
        count, cjk, uncertain, wrong = english_rates(300, seed)
        assert (cjk, uncertain, wrong) == (0, 0, 0), seed
    assert detect_encoding(srt(apostrophes_only(20)).encode("cp1252")) == "cp1252"


# ── Pairing by hand in the Preview step ───────────────────────────────────────

def pump(condition, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QApplication.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def window(qapp, monkeypatch):
    from gui.dialogs import messages
    for kind in ("info", "warn", "error"):
        monkeypatch.setattr(messages, kind, lambda *a, **k: None)
    monkeypatch.setattr(messages, "confirm", lambda *a, **k: True)
    from gui.app import AnimeSubToolApp
    w = AnimeSubToolApp()
    yield w
    for name in ("_process_worker", "_scan_worker"):
        worker = getattr(w, name, None)
        if worker is not None and worker.isRunning():
            assert worker.wait(30_000)
    w.close()
    QApplication.processEvents()


@pytest.fixture
def season(tmp_path):
    for n in (1, 2, 3):
        (tmp_path / f"Show - {n:02d}.mkv").write_bytes(b"video")
    write_srt(tmp_path / "Show - 01.srt")
    write_srt(tmp_path / "Show - 02.srt")
    write_srt(tmp_path / "Extra subs.srt")
    return tmp_path


def scanned(window, folder):
    window.folder_picker.set_path(str(folder))
    window._run_scan()
    assert pump(lambda: window._merge_step == 1 and window._scan_worker is None)
    return window.preview_panel


def sub_named(panel, name):
    return next(s for s in panel.scan_result.subtitle_files if s.filename == name)


def row_texts(panel, row):
    return [panel.table.item(row, c).text() for c in range(5)]


def test_pick_another_subtitle_none_and_move(window, season):
    panel = scanned(window, season)
    table = panel.table
    assert row_texts(panel, 2)[2].startswith("— No match —") and row_texts(panel, 2)[4] == "NO SUB"
    assert "1 WITHOUT SUBTITLE" in panel.summary_label.text()
    assert "1 SUBTITLE(S) UNUSED" in panel.summary_label.text()
    # only the subtitle cells are editable, and they say how
    assert table.item(0, 2).flags() & Qt.ItemFlag.ItemIsEditable
    assert not table.item(0, 1).flags() & Qt.ItemFlag.ItemIsEditable
    assert "rescanned" in table.item(0, 2).toolTip()
    assert "rescanned" in table.horizontalHeaderItem(2).toolTip()

    # 1) an unused subtitle for episode 3
    panel.choose_subtitle(2, sub_named(panel, "Extra subs.srt"))
    m = panel.scan_result.matches[2]
    assert m.subtitle.filename == "Extra subs.srt" and m.confidence == MatchConfidence.MANUAL
    assert row_texts(panel, 2)[3] == "MANUAL" and row_texts(panel, 2)[4] == "READY"
    assert "WITHOUT SUBTITLE" not in panel.summary_label.text()
    assert "UNUSED" not in panel.summary_label.text()
    assert "1 PAIRED BY HAND" in panel.summary_label.text()
    assert window.scan_result.unmatched_videos == []

    # 2) none for episode 1
    panel.choose_subtitle(0, None)
    assert panel.scan_result.matches[0].subtitle is None
    assert row_texts(panel, 0)[4] == "NO SUB" and "none" in row_texts(panel, 0)[2]
    assert "1 WITHOUT SUBTITLE" in panel.summary_label.text()
    assert "1 SUBTITLE(S) UNUSED" in panel.summary_label.text()          # Show - 01.srt
    assert [s.filename for s in window.scan_result.unmatched_subtitles] == ["Show - 01.srt"]

    # 3) move: episode 1 takes episode 2's subtitle; episode 2 is left without
    messages = []
    panel.status_message.connect(messages.append)
    panel.choose_subtitle(0, sub_named(panel, "Show - 02.srt"))
    matches = panel.scan_result.matches
    assert matches[0].subtitle.filename == "Show - 02.srt"
    # R5-08: the emptied row is a normal NO SUB row, not one chosen by hand
    assert matches[1].subtitle is None and not matches[1].is_manual and matches[1].moved_to == "1"
    assert row_texts(panel, 1)[4] == "NO SUB"
    assert row_texts(panel, 1)[2].startswith("— none (moved to EP 1) —")
    assert "moved from episode 2" in messages[-1]
    used = [m.subtitle.filepath for m in matches if m.subtitle]
    assert len(used) == len(set(used))                                     # one row per subtitle
    assert "1 WITHOUT SUBTITLE" in panel.summary_label.text()
    assert "1 SUBTITLE(S) UNUSED" in panel.summary_label.text()


def test_processing_uses_the_edited_pairs(window, season, monkeypatch):
    seen = {}

    def fake_batch(self, scan_result, options, progress_callback=None, log_callback=None):
        seen["pairs"] = [(m.video.filename, m.subtitle.filename if m.subtitle else None)
                         for m in scan_result.matches]
        return BatchResult(total=3, successful=2, skipped=1,
                           results=[ProcessingResult(status=S.COMPLETED)] * 2
                           + [ProcessingResult(status=S.SKIPPED)])

    monkeypatch.setattr(ProcessingEngine, "process_batch", fake_batch)
    panel = scanned(window, season)
    panel.choose_subtitle(2, sub_named(panel, "Extra subs.srt"))
    panel.choose_subtitle(0, sub_named(panel, "Show - 02.srt"))           # moves it from ep 2
    window._start_processing()
    assert pump(lambda: window._merge_step == 3 and window._process_worker is None)
    assert seen["pairs"] == [("Show - 01.mkv", "Show - 02.srt"), ("Show - 02.mkv", None),
                             ("Show - 03.mkv", "Extra subs.srt")]


def test_picker_dropdown_and_keyboard(window, season):
    panel = scanned(window, season)
    table = panel.table
    delegate = table.itemDelegateForColumn(2)
    index = table.model().index(2, 2)
    editor = delegate.createEditor(table.viewport(), None, index)
    labels = [editor.itemText(i) for i in range(editor.count())]
    assert labels[0] == "— none —"
    assert any(label.startswith("Show - 01.srt") and "now on EP 1" in label for label in labels)
    assert "Extra subs.srt" in labels and editor.currentIndex() == 0      # episode 3 has none
    editor.setCurrentIndex(labels.index("Extra subs.srt"))
    delegate.setModelData(editor, table.model(), index)
    assert panel.scan_result.matches[2].subtitle.filename == "Extra subs.srt"
    assert row_texts(panel, 2)[3] == "MANUAL"
    editor.deleteLater()

    editor = delegate.createEditor(table.viewport(), None, table.model().index(0, 2))
    assert editor.currentText() == "Show - 01.srt"                         # current one selected
    editor.setCurrentIndex(0)
    delegate.setModelData(editor, table.model(), table.model().index(0, 2))
    assert panel.scan_result.matches[0].subtitle is None
    editor.deleteLater()

    # Keyboard: Enter on a row opens its picker; double-click / F2 are edit triggers
    triggers = table.editTriggers()
    assert triggers & QTableWidget.EditTrigger.DoubleClicked
    assert triggers & QTableWidget.EditTrigger.EditKeyPressed
    table.setCurrentCell(1, 0)
    QApplication.sendEvent(table, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return,
                                            Qt.KeyboardModifier.NoModifier))
    assert table.state() == QTableWidget.State.EditingState
    assert table.currentColumn() == 2 and table.currentRow() == 1


def test_language_change_rematches_but_keeps_manual_choices_and_rescan_resets(window, tmp_path):
    for n in (1, 2):
        (tmp_path / f"Show - {n:02d}.mkv").write_bytes(b"v")
        write_srt(tmp_path / f"Show - {n:02d}.ar.srt")
        write_srt(tmp_path / f"Show - {n:02d}.en.srt")
    window.options_panel.sub_lang_combo.set_value("ara")
    panel = scanned(window, tmp_path)
    assert [m.subtitle.filename for m in panel.scan_result.matches] == ["Show - 01.ar.srt", "Show - 02.ar.srt"]
    assert "Arabic (ara)" in panel.table.item(0, 2).toolTip()
    panel.choose_subtitle(1, sub_named(panel, "Show - 02.en.srt"))          # by hand
    assert panel.table.item(1, 4).text() == "⚠ CHECK"
    assert "subtitle looks like English, track will be labelled Arabic" in panel.table.item(1, 4).toolTip()

    window.options_panel.sub_lang_combo.set_value("eng")                    # signal -> rematch
    matches = panel.scan_result.matches
    assert matches[0].subtitle.filename == "Show - 01.en.srt"               # re-matched
    assert matches[1].subtitle.filename == "Show - 02.en.srt" and matches[1].is_manual
    assert panel.table.item(1, 4).text() == "READY"
    assert window.options_panel.get_options().subtitle_language == "eng"

    window._run_scan()                                                       # rescan: reset
    assert pump(lambda: window._scan_worker is None and panel.scan_result is window.scan_result
                and not any(m.is_manual for m in window.scan_result.matches))
    assert [m.subtitle.filename for m in window.scan_result.matches] == ["Show - 01.en.srt", "Show - 02.en.srt"]


def test_preview_flags_a_subtitle_in_another_language(window, tmp_path):
    (tmp_path / "Show - 01.mkv").write_bytes(b"v")
    write_srt(tmp_path / "Show - 01 [ENG].srt")
    window.options_panel.sub_lang_combo.set_value("ara")
    panel = scanned(window, tmp_path)
    assert panel.table.item(0, 4).text() == "⚠ CHECK"
    assert "track will be labelled Arabic" in panel.table.item(0, 4).toolTip()
    assert "English (eng)" in panel.table.item(0, 2).toolTip()
    assert "1 TO CHECK" in panel.summary_label.text()
