"""Round 6 findings: a marker word in a show's title never costs it its own
subtitle (R6-01) and a LOW pair is listed by the CLI; the wanted language beats
an untagged subtitle once the title score is at least 50 (R6-02); a partial
track is recognised when the title has the same word (R6-03) and the leading
group tag is ignored (R6-04); 'Film' / 'Movie' inside a title is not a film
marker (R6-05); years do not lower the title score (R6-06)."""

import itertools
import random
from pathlib import Path

import pytest
from click.testing import CliRunner

from conftest import write_srt
from core.matcher import _is_film_marked, _normalize_title, extract_episode_info, match_files
from core.models import BatchResult, MatchConfidence, ProcessingResult, ProcessingStatus


def info(name: str):
    return extract_episode_info(Path("C:/season") / name)


def pairs(videos, subs, language="ara"):
    matches, unmatched_v, unmatched_s = match_files(
        [info(v) for v in videos], [info(s) for s in subs], language)
    return ({m.video.filename: (m.subtitle.filename if m.subtitle else None) for m in matches},
            matches, unmatched_v, unmatched_s)


def every_order(videos, subs, language="ara"):
    for v, s in itertools.product(itertools.permutations(videos), itertools.permutations(subs)):
        yield pairs(list(v), list(s), language)


# ── R6-01: a marker word in the title ─────────────────────────────────────────

MARKER_TITLES = [
    ("[SubsPlease] Special A - 03 (1080p).mkv", "[SubsPlease] Sousou no Frieren - 03 (1080p).mkv",
     "Special A - 03"),
    ("[SubsPlease] Happy Ending - 02 (1080p).mkv", "[SubsPlease] Oshi no Ko - 02 (1080p).mkv",
     "Happy Ending - 02"),
    ("[SubsPlease] Opening Night - 07 (1080p).mkv", "[SubsPlease] Dandadan - 07 (1080p).mkv",
     "Opening Night - 07"),
    ("[SubsPlease] Preview Rangers - 04 (1080p).mkv", "[SubsPlease] Kaiju No 8 - 04 (1080p).mkv",
     "Preview Rangers - 04"),
    ("[SubsPlease] Trailer Hitch - 05 (1080p).mkv", "[SubsPlease] Mushishi - 05 (1080p).mkv",
     "Trailer Hitch - 05"),
]


@pytest.mark.parametrize("language", ["ara", ""])
@pytest.mark.parametrize("suffix", [".ar.srt", ".srt", ".en.ass"])
@pytest.mark.parametrize("marked, other, sub_title", MARKER_TITLES)
def test_a_marker_word_in_the_title_keeps_its_own_subtitle(marked, other, sub_title, suffix,
                                                           language):
    assert info(marked).extra_kind == ""
    sub = sub_title + suffix
    for got, matches, unmatched_v, unmatched_s in every_order([marked, other], [sub], language):
        assert got == {marked: sub, other: None}
        assert [v.filename for v in unmatched_v] == [other] and not unmatched_s


def test_all_marker_titles_in_one_folder():
    videos = [v for row in MARKER_TITLES for v in row[:2]]
    subs = [row[2] + ".ar.srt" for row in MARKER_TITLES]
    for seed in range(30):
        v, s = videos[:], subs[:]
        random.Random(seed).shuffle(v)
        random.Random(seed + 100).shuffle(s)
        got, _, _, _ = pairs(v, s)
        for marked, other, sub_title in MARKER_TITLES:
            assert got[marked] == sub_title + ".ar.srt"
            assert got[other] is None


def test_plain_video_still_beats_an_unrecognised_marker_video_of_the_same_show():
    odd = "Show - 01 [Preview v2].mkv"
    for got, _, _, _ in every_order([odd, "Show - 01.mkv"], ["Show - 01.srt"]):
        assert got == {odd: None, "Show - 01.mkv": "Show - 01.srt"}


@pytest.fixture
def cli(monkeypatch):
    import cli.commands as commands
    monkeypatch.setattr(commands, "setup_logging", lambda **kw: None)
    return commands


@pytest.fixture
def low_folder(tmp_path):
    (tmp_path / "[SubsPlease] Sousou no Frieren - 03 (1080p).mkv").write_bytes(b"v")
    write_srt(tmp_path / "Special A - 03.ar.srt")
    return tmp_path


LOW_WARNING = "the titles look different (title match"


def test_low_pair_is_low(low_folder):
    got, matches, _, _ = pairs(["[SubsPlease] Sousou no Frieren - 03 (1080p).mkv"],
                               ["Special A - 03.ar.srt"])
    assert matches[0].confidence == MatchConfidence.LOW and matches[0].score < 50


def test_cli_lists_a_low_pair_in_scan_and_preview(cli, low_folder):
    for command in ("scan", "preview"):
        out = CliRunner().invoke(cli.cli, [command, str(low_folder)]).output
        assert LOW_WARNING in out, command
        assert "1 pair(s) to check" in out, command
        assert "Special A - 03.ar.srt" in out, command


def test_cli_lists_a_low_pair_before_processing(cli, low_folder, monkeypatch):
    def fake_batch(self, scan_result, options, progress_callback=None, log_callback=None):
        log_callback("BATCH STARTED")
        return BatchResult(total=1, successful=1,
                           results=[ProcessingResult(status=ProcessingStatus.COMPLETED)])

    monkeypatch.setattr(cli, "validate_mkvtoolnix", lambda tools: "mkvmerge v100")
    monkeypatch.setattr(cli.ProcessingEngine, "process_batch", fake_batch)
    out = CliRunner().invoke(cli.cli, ["process", str(low_folder), "-y"]).output
    assert "1 pair(s) to check" in out
    assert out.index(LOW_WARNING) < out.index("BATCH STARTED")
    out = CliRunner().invoke(cli.cli, ["process", str(low_folder)], input="n\n").output
    assert out.index(LOW_WARNING) < out.index("Proceed with processing?")


def test_cli_does_not_flag_a_good_pair(cli, tmp_path):
    (tmp_path / "Show - 01.mkv").write_bytes(b"v")
    write_srt(tmp_path / "Show - 01.ar.srt")
    out = CliRunner().invoke(cli.cli, ["scan", str(tmp_path)]).output
    assert LOW_WARNING not in out and "to check" not in out


# ── R6-02: the wanted language beats an untagged exact title ──────────────────

LANGUAGE_CASES = [
    ("[SubsPlease] Dandadan - 05 (1080p).mkv", "Dan Da Dan - 05.ar.srt", "Dandadan - 05.srt"),
    ("[SubsPlease] Boku no Hero Academia - 05 (1080p).mkv", "My Hero Academia - 05.ar.srt",
     "Boku no Hero Academia - 05.srt"),
    ("[SubsPlease] Kimetsu no Yaiba - 05 (1080p).mkv", "Demon Slayer Kimetsu no Yaiba - 05.ar.srt",
     "Kimetsu no Yaiba - 05.srt"),
    ("[SubsPlease] Sousou no Frieren - 05 (1080p).mkv", "Frieren - 05.ar.srt",
     "Sousou no Frieren - 05.srt"),
]


@pytest.mark.parametrize("video, wanted, untagged", LANGUAGE_CASES)
def test_wanted_language_beats_an_untagged_exact_title(video, wanted, untagged):
    for got, matches, _, unmatched_s in every_order([video], [wanted, untagged]):
        assert matches[0].score >= 50
        assert got == {video: wanted}
        assert [s.filename for s in unmatched_s] == [untagged]
        assert matches[0].language_warning == ""


@pytest.mark.parametrize("video, wanted, untagged", LANGUAGE_CASES)
def test_another_language_still_loses_to_an_untagged_one(video, wanted, untagged):
    other = wanted.replace(".ar.", ".en.")
    for got, _, _, _ in every_order([video], [other, untagged]):
        assert got == {video: untagged}


@pytest.mark.parametrize("video, wanted, untagged", LANGUAGE_CASES)
def test_without_a_wanted_language_the_closest_title_wins(video, wanted, untagged):
    for got, _, _, _ in every_order([video], [wanted, untagged], language=""):
        assert got == {video: untagged}


def test_a_whole_dandadan_season_takes_the_arabic_subtitles():
    videos = [f"[SubsPlease] Dandadan - {n:02d} (1080p).mkv" for n in range(1, 13)]
    subs = ([f"Dan Da Dan - {n:02d}.ar.srt" for n in range(1, 13)]
            + [f"Dandadan - {n:02d}.srt" for n in range(1, 13)])
    for seed in range(25):
        v, s = videos[:], subs[:]
        random.Random(seed).shuffle(v)
        random.Random(seed + 7).shuffle(s)
        got, _, _, unmatched_s = pairs(v, s)
        assert got == {f"[SubsPlease] Dandadan - {n:02d} (1080p).mkv": f"Dan Da Dan - {n:02d}.ar.srt"
                       for n in range(1, 13)}
        assert sorted(x.filename for x in unmatched_s) == sorted(subs[12:])


def test_unrelated_untagged_title_below_50_still_loses_to_another_language():
    for got, _, _, _ in every_order(["Frieren - 01.mkv"],
                                    ["Frieren - 01.en.srt", "Oshi no Ko - 01.srt"]):
        assert got == {"Frieren - 01.mkv": "Frieren - 01.en.srt"}


def test_a_wanted_language_below_50_loses_to_a_well_titled_untagged_one():
    for got, _, _, _ in every_order(["Frieren - 01.mkv"],
                                    ["Oshi no Ko - 01.ar.srt", "Frieren - 01.srt"]):
        assert got == {"Frieren - 01.mkv": "Frieren - 01.srt"}


# ── R6-03 / R6-04: partial tracks and the title / group tag ───────────────────

@pytest.mark.parametrize("video, full, partial, word", [
    ("Signs of Love - 05.mkv", "[Grp] Signs of Love - 05.ass", "Signs of Love - 05 [Signs].ass",
     "signs"),
    ("Karaoke Club - 02.mkv", "[Grp] Karaoke Club - 02.ass", "Karaoke Club - 02 [Karaoke].ass",
     "karaoke"),
    ("[SubsPlease] Karaoke Club - 02 (1080p).mkv", "Karaoke Club - 02.ass",
     "Karaoke Club - 02.karaoke.ass", "karaoke"),
    ("Old Boy - 03.mkv", "Old Boy - 03.srt", "Old Boy - 03 old.srt", "old"),
])
def test_partial_track_recognised_when_the_title_has_the_word(video, full, partial, word):
    for got, matches, _, unmatched_s in every_order([video], [full, partial]):
        assert got == {video: full}
        assert matches[0].note == ""
        assert [s.filename for s in unmatched_s] == [partial]
    _, matches, _, _ = pairs([video], [partial])
    assert matches[0].confidence == MatchConfidence.MEDIUM
    assert f"partial or alternative track ({word})" in matches[0].note


@pytest.mark.parametrize("video, sub", [
    ("Signs of Love - 05.mkv", "[Grp] Signs of Love - 05.ass"),
    ("Oshi no Ko - 03.mkv", "[Old Group] Oshi no Ko - 03.ass"),
    ("[SubsPlease] Oshi no Ko - 03 (1080p).mkv", "[Old Group] Oshi no Ko - 03.ar.ass"),
    ("[Copy Cats] Show - 03.mkv", "[Copy Cats] Show - 03.srt"),
])
def test_title_and_group_tag_words_are_not_partial_markers(video, sub):
    _, matches, _, _ = pairs([video], [sub])
    assert matches[0].subtitle.filename == sub
    assert matches[0].note == ""
    assert matches[0].confidence in (MatchConfidence.EXACT, MatchConfidence.HIGH)


def test_old_group_full_track_beats_a_real_old_track():
    video = "Oshi no Ko - 03.mkv"
    full, old = "[Old Group] Oshi no Ko - 03.ass", "Oshi no Ko - 03 [Old].ass"
    for got, _, _, _ in every_order([video], [full, old]):
        assert got == {video: full}


# ── R6-05: 'Film' / 'Movie' inside a title ────────────────────────────────────

@pytest.mark.parametrize("video, sub", [
    ("[SubsPlease] Eiga Bu - 03.mkv", "Film Club - 03.en.srt"),
    ("[SubsPlease] Film Club - 03 (1080p).mkv", "Film Club - 03.ar.srt"),
    ("[Grp] Movie Maker - 01 [1080p].mkv", "Movie Maker - 01.ar.srt"),
])
def test_film_or_movie_inside_a_title_is_not_a_film(video, sub):
    got, _, unmatched_v, unmatched_s = pairs([video], [sub])
    assert got == {video: sub}
    assert not unmatched_v and not unmatched_s


@pytest.mark.parametrize("name, marked", [
    ("Detective Conan Movie 26.mkv", True),
    ("[Group] Detective Conan Movie 26 [1080p].mkv", True),
    ("Show Film 3.mkv", True),
    ("Film 2.mkv", True),
    ("Show the Movie.mkv", True),
    ("Show Movie [1080p].mkv", True),
    ("Show The Movie.ar.srt", True),
    ("Gekijouban Show - 01.mkv", True),
    ("劇場版 Show - 01.mkv", True),
    ("Film Club - 03.en.srt", False),
    ("[Grp] Movie Maker - 01 [1080p].mkv", False),
    ("Eiga Bu - 03.mkv", False),
])
def test_film_marker(name, marked):
    assert _is_film_marked(info(name)) is marked


# ── R6-06: years ──────────────────────────────────────────────────────────────

def test_a_year_in_the_title_does_not_lower_the_score():
    for got, matches, _, _ in every_order(["Show 2023 - 01.mkv"], ["Show (2023) - 01.ar.srt"]):
        assert got == {"Show 2023 - 01.mkv": "Show (2023) - 01.ar.srt"}
        assert matches[0].score == 100.0
        assert matches[0].confidence == MatchConfidence.HIGH


def test_normalize_title_keeps_a_year_that_is_the_whole_title():
    assert _normalize_title("Show 2023") == "show"
    assert _normalize_title("1917") == "1917"


@pytest.mark.parametrize("video, sub", [
    ("2012.2009.1080p.BluRay.x264-GRP.mkv", "2012.srt"),
    ("2012.2009.1080p.BluRay.x264-GRP.mkv", "2012.ar.srt"),
    ("1917.mkv", "1917.srt"),
    ("1917 (2019) [1080p].mkv", "1917.srt"),
])
def test_a_year_titled_film_pairs(video, sub):
    got, matches, _, _ = pairs([video], [sub])
    assert got == {video: sub}
