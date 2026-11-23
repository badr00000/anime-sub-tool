"""Round 5 findings: a partial/variant subtitle never beats the full one (R5-01);
seasons are not swapped (R5-02); films whose name ends in a year pair (R5-03);
a Watch-folder rescan keeps the subtitles picked by hand (R5-04); an unrelated
show never beats a well-titled subtitle in another language (R5-05); a 'Movie N'
never takes episode N's subtitle (R5-06); the CLI warns in preview and process
too (R5-07); a row emptied by a move is a normal NO SUB row (R5-08)."""

import itertools
import random
import time
from pathlib import Path

import pytest
from click.testing import CliRunner
from PySide6.QtWidgets import QApplication

from conftest import write_srt
from core.engine import ProcessingEngine
from core.matcher import extract_episode_info, match_files, set_manual_subtitle
from core.models import BatchResult, MatchConfidence, ProcessingResult, ProcessingStatus


def info(name: str):
    return extract_episode_info(Path("C:/season") / name)


def pairs(videos, subs, language="ara"):
    matches, unmatched_v, unmatched_s = match_files(
        [info(v) for v in videos], [info(s) for s in subs], language)
    return ({m.video.filename: (m.subtitle.filename if m.subtitle else None) for m in matches},
            matches, unmatched_v, unmatched_s)


def every_order(videos, subs, language="ara", limit=None):
    """Yield the pairing for every order of the videos and of the subtitles."""
    video_orders = list(itertools.permutations(videos))
    sub_orders = list(itertools.permutations(subs))
    combos = list(itertools.product(video_orders, sub_orders))
    if limit and len(combos) > limit:
        combos = random.Random(5).sample(combos, limit)
    for v, s in combos:
        yield pairs(list(v), list(s), language)


# ── R5-01: the full subtitle beats partial / variant ones ─────────────────────

VARIANTS = [
    "Show - 03 alt.srt", "Show - 03 (Signs & Songs).ass", "Show - 03 [Forced].srt",
    "Show - 03.signs.ass", "Show - 03 (CC).srt", "Show - 03.forced.srt", "Show - 03 [Signs].ass",
    "Show - 03 songs.ass", "Show - 03 - Copy.srt", "Show - 03 S&S.ass", "Show - 03 karaoke.ass",
    "Show - 03 commentary.srt", "Show - 03 SDH.srt", "Show - 03 old.srt", "Show - 03 (Preview).srt",
    "Show - 03 [Signs&Songs].ass",
]


@pytest.mark.parametrize("full", ["Show - 03.srt", "Show - 03.ass"])
@pytest.mark.parametrize("variant", VARIANTS)
def test_full_subtitle_beats_a_variant_in_every_order(full, variant):
    for got, matches, _, unmatched_s in every_order(["Show - 03.mkv"], [full, variant]):
        assert got == {"Show - 03.mkv": full}
        assert matches[0].note == "" and matches[0].confidence == MatchConfidence.EXACT
        assert [s.filename for s in unmatched_s] == [variant]


@pytest.mark.parametrize("full", ["Show - 03.srt", "Show - 03.ass"])
def test_full_subtitle_beats_all_variants_together(full):
    names = VARIANTS + [full]
    for seed in range(40):
        order = names[:]
        random.Random(seed).shuffle(order)
        got, _, _, _ = pairs(["Show - 03.mkv"], order)
        assert got == {"Show - 03.mkv": full}


def test_a_lone_variant_still_pairs_but_is_flagged():
    got, matches, _, _ = pairs(["Show - 03.mkv"], ["Show - 03 [Signs].ass"])
    assert got == {"Show - 03.mkv": "Show - 03 [Signs].ass"}
    assert matches[0].confidence == MatchConfidence.MEDIUM
    assert "partial or alternative track (signs)" in matches[0].note


def test_a_partial_word_shared_with_the_video_title_does_not_count():
    got, matches, _, _ = pairs(["Old Boy - 01.mkv"], ["Old Boy - 01.srt"])
    assert got == {"Old Boy - 01.mkv": "Old Boy - 01.srt"} and matches[0].note == ""
    got, _, _, _ = pairs(["Old Boy - 01.mkv"], ["Old Boy - 01 [Forced].srt", "Old Boy - 01.srt"])
    assert got == {"Old Boy - 01.mkv": "Old Boy - 01.srt"}


@pytest.mark.parametrize("subs, chosen", [
    (["Show - 03.srt", "Show - 03v2.srt"], "Show - 03v2.srt"),              # version preference
    (["Show - 03.srt", "Show - 03.synced.srt"], "Show - 03.synced.srt"),    # synced replaces it
    (["Show - 03.ass", "Show - 03.synced.srt"], "Show - 03.synced.srt"),
    (["[Group] Show - 03.srt", "Show - 03.srt"], "Show - 03.srt"),          # named like the video
    (["Show - 03.srt", "Show - 03 [Arabic].srt"], "Show - 03 [Arabic].srt"),  # wanted language
    (["Show - 03.ar.srt", "Show - 03 alt.ar.srt"], "Show - 03.ar.srt"),
    (["Show - 03v2.srt", "Show - 03 [Signs].ass", "Show - 03.srt"], "Show - 03v2.srt"),
])
def test_preferences_hold_in_every_order(subs, chosen):
    for got, _, _, _ in every_order(["Show - 03.mkv"], subs):
        assert got == {"Show - 03.mkv": chosen}


def test_equal_pairs_are_decided_by_name_not_input_order():
    results = {pairs(["Show - 03.mkv"], s)[0]["Show - 03.mkv"]
               for s in itertools.permutations(["Show - 03.srt", "Show - 03.ass", "Show - 03.ssa"])}
    assert len(results) == 1
    # two videos that want the same subtitle equally
    results = {tuple(sorted(pairs(v, ["Show - 03.srt"])[0].items()))
               for v in itertools.permutations(["Show - 03.mkv", "Show - 03.mp4"])}
    assert len(results) == 1


# ── R5-02: seasons ────────────────────────────────────────────────────────────

def _season_case(s1_video, s2_video, s1_sub, s2_sub, eps=(1, 2)):
    videos = [s1_video.format(n) for n in eps] + [s2_video.format(n) for n in eps]
    subs = [s1_sub.format(n) for n in eps] + [s2_sub.format(n) for n in eps]
    expected = {s1_video.format(n): s1_sub.format(n) for n in eps}
    expected.update({s2_video.format(n): s2_sub.format(n) for n in eps})
    return videos, subs, expected


SEASON_FOLDERS = [
    ("[SubsPlease] Oshi no Ko - {:02d} (1080p).mkv", "[Erai-raws] Oshi no Ko 2nd Season - {:02d} [1080p].mkv",
     "Oshi no Ko - {:02d}.ar.srt", "Oshi no Ko S2 - {:02d}.ar.srt"),
    ("Show - {:02d}.mkv", "Show S2 - {:02d}.mkv", "Show - {:02d}.srt", "Show S2 - {:02d} [Arabic].srt"),
    ("Show - {:02d}.mkv", "Show S2 - {:02d}.mkv", "Show - {:02d}.srt", "[AR] Show S2 - {:02d}.srt"),
    ("Show - {:02d}.mkv", "Show S2 - {:02d}.mkv", "Show - {:02d}.srt", "Show S2 - {:02d}.srt"),
    ("Show - {:02d}.mkv", "Show Season 2 - {:02d}.mkv", "Show - {:02d}.srt", "Show S02E{:02d}.srt"),
]


@pytest.mark.parametrize("folder", SEASON_FOLDERS, ids=lambda f: f[1][:24])
def test_seasons_are_never_swapped_in_any_order(folder):
    videos, subs, expected = _season_case(*folder)
    for got, matches, unmatched_v, unmatched_s in every_order(videos, subs):
        assert got == expected
        assert not unmatched_v and not unmatched_s
        for m in matches:
            assert m.note == ""
            assert m.confidence in (MatchConfidence.EXACT, MatchConfidence.HIGH)


def test_a_missing_season_1_subtitle_is_not_replaced_by_season_2():
    videos = ["Show - 01.mkv", "Show - 02.mkv", "Show S2 - 01.mkv", "Show S2 - 02.mkv"]
    subs = ["Show - 01.srt", "Show S2 - 01.srt", "Show S2 - 02.srt"]
    for got, _, unmatched_v, _ in every_order(videos, subs):
        assert got == {"Show - 01.mkv": "Show - 01.srt", "Show - 02.mkv": None,
                       "Show S2 - 01.mkv": "Show S2 - 01.srt", "Show S2 - 02.mkv": "Show S2 - 02.srt"}
        assert [v.filename for v in unmatched_v] == ["Show - 02.mkv"]


@pytest.mark.parametrize("video, sub, says", [
    ("Show - 02.mkv", "Show S2 - 02.srt", "the subtitle is season 2"),
    ("Show S2 - 02.mkv", "Show - 02.srt", "the episode is season 2"),
    ("[Erai-raws] Oshi no Ko 2nd Season - 01 [1080p].mkv", "Oshi no Ko - 01.ar.srt", "the episode is season 2"),
])
def test_a_lone_other_season_candidate_pairs_but_is_flagged(video, sub, says):
    got, matches, _, _ = pairs([video], [sub])
    assert got == {video: sub}
    assert matches[0].confidence == MatchConfidence.MEDIUM
    assert says in matches[0].note


def test_season_1_stated_or_not_is_the_same_season():
    got, matches, _, _ = pairs(["Show S01E02.mkv"], ["Show - 02.srt"])
    assert got == {"Show S01E02.mkv": "Show - 02.srt"} and matches[0].note == ""


# ── R5-03: films whose name ends in a year ────────────────────────────────────

@pytest.mark.parametrize("video, sub", [
    ("Perfect Blue 1997.mkv", "Perfect Blue 1997.ar.srt"),
    ("Perfect Blue 1997.mkv", "Perfect Blue 1997.srt"),
    ("Perfect Blue 1997.mkv", "Perfect Blue.ar.srt"),
    ("Your Name 2016.mkv", "Your Name 2016.ar.srt"),
    ("Josee to Tora to Sakana-tachi 2020.mkv", "Josee to Tora to Sakana-tachi 2020.ar.srt"),
    ("Perfect_Blue_1997_1080p.mkv", "Perfect Blue 1997.ar.srt"),
    ("1917.mkv", "1917.ar.srt"),
])
def test_films_ending_in_a_year_pair(video, sub):
    got, matches, unmatched_v, unmatched_s = pairs([video], [sub])
    assert got == {video: sub} and not unmatched_v and not unmatched_s
    assert matches[0].score == 100


@pytest.mark.parametrize("name, episode", [
    ("Perfect Blue 1997.mkv", None), ("Perfect Blue 1997.ar.srt", None),
    ("Your Name 2016.mkv", None), ("Show 2023.mkv", None), ("1917.mkv", None),
    ("One Piece - 1071.mkv", "1071"), ("One Piece - 1071.ar.srt", "1071"),
    ("Show - 2023.mkv", "2023"),                 # a year-like number after ' - ' is an episode
    ("Show Episode 2023.mkv", "2023"), ("Show S01E2023.mkv", "2023"),
    ("Show - 01.en.srt", "1"), ("Show - 01.ar.srt", "1"),
])
def test_years_are_not_episode_numbers(name, episode):
    assert info(name).episode_num == episode


def test_language_is_still_read_from_the_full_subtitle_name():
    assert info("Perfect Blue 1997.ar.srt").language == "ara"
    assert info("Tenki.no.Ko.srt").language == "kor"           # as before: the name says ko


# ── R5-05: an unrelated untagged show ─────────────────────────────────────────

@pytest.mark.parametrize("subs", [
    ["Frieren - 01.en.srt", "Oshi no Ko - 01.srt"], ["Oshi no Ko - 01.srt", "Frieren - 01.en.srt"],
])
def test_unrelated_untagged_show_loses_to_another_language(subs):
    got, matches, _, unmatched_s = pairs(["Frieren - 01.mkv"], subs, "ara")
    assert got == {"Frieren - 01.mkv": "Frieren - 01.en.srt"}
    assert matches[0].language_warning == "subtitle looks like English, track will be labelled Arabic"
    assert [s.filename for s in unmatched_s] == ["Oshi no Ko - 01.srt"]


# ── R5-06: 'Movie N' is not episode N ─────────────────────────────────────────

@pytest.mark.parametrize("video, sub", [
    ("Detective Conan Movie 26.mkv", "Detective Conan - 26.srt"),
    ("[Group] Detective Conan Movie 26 [1080p].mkv", "Detective Conan - 26.ar.srt"),
    ("Show Film 3.mkv", "Show - 03.srt"),
    ("Detective Conan - 26.mkv", "Detective Conan Movie 26.srt"),
])
def test_a_film_never_takes_an_episode_subtitle(video, sub):
    got, _, unmatched_v, unmatched_s = pairs([video], [sub])
    assert got == {video: None}
    assert len(unmatched_v) == 1 and len(unmatched_s) == 1


@pytest.mark.parametrize("video, sub", [
    ("Detective Conan Movie 26.mkv", "Detective Conan Movie 26.ar.srt"),
    ("[Group] Detective Conan Movie 26 [1080p].mkv", "Detective Conan Movie 26.srt"),
    ("Gekijouban Show.mkv", "Gekijouban Show.ar.srt"),
])
def test_a_film_pairs_with_its_own_subtitle(video, sub):
    got, _, _, _ = pairs([video], [sub])
    assert got == {video: sub}


def test_conan_movie_and_episode_in_one_folder():
    videos = ["Detective Conan Movie 26.mkv", "Detective Conan - 26.mkv"]
    subs = ["Detective Conan - 26.srt", "Detective Conan Movie 26.srt"]
    for got, _, _, _ in every_order(videos, subs):
        assert got == {"Detective Conan Movie 26.mkv": "Detective Conan Movie 26.srt",
                       "Detective Conan - 26.mkv": "Detective Conan - 26.srt"}


# ── R5-08: a row emptied by a move ────────────────────────────────────────────

def test_moved_from_row_is_a_normal_unmatched_row():
    matches, _, _ = match_files([info("Show - 01.mkv"), info("Show - 02.mkv")],
                                [info("Show - 01.srt"), info("Show - 02.srt")], "ara")
    moved_from = set_manual_subtitle(matches, 0, matches[1].subtitle, "ara")
    assert moved_from == 1
    assert matches[0].is_manual and matches[0].subtitle.filename == "Show - 02.srt"
    assert matches[1].subtitle is None and not matches[1].is_manual
    assert matches[1].confidence == MatchConfidence.NO_MATCH and matches[1].moved_to == "1"


# ── R5-07: CLI warnings in preview and process ────────────────────────────────

@pytest.fixture
def cli(monkeypatch):
    import cli.commands as commands
    monkeypatch.setattr(commands, "setup_logging", lambda **kw: None)
    return commands


@pytest.fixture
def warned_folder(tmp_path):
    (tmp_path / "Show - 01.mkv").write_bytes(b"v")
    write_srt(tmp_path / "Show - 01.en.srt")
    (tmp_path / "Show - 02.mkv").write_bytes(b"v")
    write_srt(tmp_path / "Show S2 - 02.srt")
    return tmp_path


LANGUAGE_WARNING = "subtitle looks like English, track will be labelled Arabic"


def test_cli_scan_and_preview_show_the_warnings(cli, warned_folder):
    for command in ("scan", "preview"):
        out = CliRunner().invoke(cli.cli, [command, str(warned_folder)]).output
        assert LANGUAGE_WARNING in out, command
        assert "the subtitle is season 2" in out, command


def test_cli_process_warns_before_processing_starts(cli, warned_folder, monkeypatch):
    def fake_batch(self, scan_result, options, progress_callback=None, log_callback=None):
        log_callback("BATCH STARTED")
        return BatchResult(total=2, successful=2,
                           results=[ProcessingResult(status=ProcessingStatus.COMPLETED)] * 2)

    monkeypatch.setattr(cli, "validate_mkvtoolnix", lambda tools: "mkvmerge v100")
    monkeypatch.setattr(cli.ProcessingEngine, "process_batch", fake_batch)
    out = CliRunner().invoke(cli.cli, ["process", str(warned_folder), "-y"]).output
    assert LANGUAGE_WARNING in out and "the subtitle is season 2" in out
    assert out.index(LANGUAGE_WARNING) < out.index("BATCH STARTED")
    # and before the confirmation prompt when not given -y
    out = CliRunner().invoke(cli.cli, ["process", str(warned_folder)], input="n\n").output
    assert out.index(LANGUAGE_WARNING) < out.index("Proceed with processing?")
    assert "Cancelled." in out


# ── R5-04: a Watch-folder rescan keeps the choices made by hand ───────────────

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


def rescan(window, auto):
    before = window.scan_result
    window._run_scan(auto=auto)
    assert pump(lambda: window._scan_worker is None and window.scan_result is not before
                and window.preview_panel.scan_result is window.scan_result)
    return window.preview_panel


def sub_named(panel, name):
    return next(s for s in panel.scan_result.subtitle_files if s.filename == name)


def subs_of(window):
    return [m.subtitle.filename if m.subtitle else None for m in window.scan_result.matches]


def test_watch_rescan_keeps_manual_picks_and_scan_button_resets(window, tmp_path):
    for n in (1, 2, 3):
        (tmp_path / f"Show - {n:02d}.mkv").write_bytes(b"video")
    write_srt(tmp_path / "Show - 01.srt")
    write_srt(tmp_path / "Show - 02.srt")
    write_srt(tmp_path / "Extra subs.srt")
    write_srt(tmp_path / "Other.srt")
    window.folder_picker.set_path(str(tmp_path))
    panel = rescan(window, auto=False)
    assert subs_of(window) == ["Show - 01.srt", "Show - 02.srt", None]

    panel.choose_subtitle(2, sub_named(panel, "Extra subs.srt"))
    panel.choose_subtitle(0, sub_named(panel, "Show - 02.srt"))        # moved from episode 2
    panel.choose_subtitle(1, sub_named(panel, "Other.srt"))
    expected = ["Show - 02.srt", "Other.srt", "Extra subs.srt"]
    assert subs_of(window) == expected

    # A new file arrives: the watcher's rescan keeps every pick
    (tmp_path / "Show - 04.mkv").write_bytes(b"video")
    panel = rescan(window, auto=True)
    assert subs_of(window) == expected + [None]
    assert all(m.is_manual for m in window.scan_result.matches[:3])
    assert "kept 3 subtitle choice(s)" in window.status_bar.currentMessage()
    assert "3 paired by hand" in panel.summary_label.text()

    # A picked subtitle is deleted: that pick is dropped, the others stay
    (tmp_path / "Other.srt").unlink()
    panel = rescan(window, auto=True)
    assert subs_of(window) == ["Show - 02.srt", None, "Extra subs.srt", None]
    message = window.status_bar.currentMessage()
    assert "kept 2 subtitle choice(s)" in message and "dropped 1" in message
    assert panel.table.item(1, 2).text().startswith("None, moved to episode 1")   # R5-08
    assert "2 paired by hand" in panel.summary_label.text()

    # The SCAN FOLDER button starts afresh
    rescan(window, auto=False)
    assert not any(m.is_manual for m in window.scan_result.matches)
    assert subs_of(window) == ["Show - 01.srt", "Show - 02.srt", None, None]


def test_season_and_partial_notes_show_in_the_preview(window, tmp_path):
    (tmp_path / "Show - 02.mkv").write_bytes(b"v")
    write_srt(tmp_path / "Show S2 - 02.srt")
    (tmp_path / "Show - 03.mkv").write_bytes(b"v")
    write_srt(tmp_path / "Show - 03 [Signs].srt")
    window.folder_picker.set_path(str(tmp_path))
    panel = rescan(window, auto=False)
    assert panel.table.item(0, 4).text() == "Check"
    assert "the subtitle is season 2" in panel.table.item(0, 4).toolTip()
    assert panel.table.item(1, 4).text() == "Check"
    assert "partial or alternative track" in panel.table.item(1, 4).toolTip()
    assert "2 to check" in panel.summary_label.text()
