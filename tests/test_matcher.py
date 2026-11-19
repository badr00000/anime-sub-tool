from pathlib import Path

import pytest

from core.constants import OUTPUT_MARKER
from core.matcher import extract_episode_info, list_media_files, match_files, scan_folder
from core.models import MatchConfidence


def info(name: str):
    return extract_episode_info(Path("C:/season") / name)


@pytest.mark.parametrize("name, episode", [
    ("[Group] Show - 01 [1080p].mkv", "1"),
    ("[Cleo]Mousou_Dairinin_-_01_(Dual Audio).mkv", "1"),
    ("Show S01E05 [1080p][x264].mkv", "5"),
    ("Show.S01E05.1080p.x264.mkv", "5"),
    ("Show (2004) - 07 [1080p x264].mkv", "7"),
    ("Show - 1080p - 09.mkv", "9"),
    ("[G] Show - 05 [ABCD1234].mkv", "5"),
    ("Show - 03v2.mkv", "3"),
    ("Show - 12.5.mkv", "12.5"),
    ("Show - 001.mkv", "1"),
    ("Show - 113 [720p].mkv", "113"),
    ("Show - 01.synced.srt", "1"),
    # A multi-episode file is matched by its first number
    ("Show - 01-02.mkv", "1"),
])
def test_episode_number(name, episode):
    assert info(name).episode_num == episode


@pytest.mark.parametrize("name, season", [
    ("Show S01E05.mkv", 1),
    ("Show S2 - 05.mkv", 2),
    ("Show 2nd Season - 05.mkv", 2),
    ("Show Season 3 - 05.mkv", 3),
    ("Show - 05.mkv", None),
])
def test_season(name, season):
    assert info(name).season == season


def match(videos, subs):
    return match_files([info(v) for v in videos], [info(s) for s in subs])


def test_same_name_is_exact():
    matches, unmatched_v, unmatched_s = match(["Show - 01.mkv"], ["Show - 01.srt"])
    assert matches[0].subtitle.filename == "Show - 01.srt"
    assert matches[0].confidence == MatchConfidence.EXACT
    assert matches[0].score == 100
    assert not unmatched_v and not unmatched_s


def test_season_mismatch_does_not_match():
    matches, unmatched_v, unmatched_s = match(["Show S01E05.mkv"], ["Show S02E05.srt"])
    assert matches[0].subtitle is None
    assert matches[0].confidence == MatchConfidence.NO_MATCH
    assert [v.filename for v in unmatched_v] == ["Show S01E05.mkv"]
    assert [s.filename for s in unmatched_s] == ["Show S02E05.srt"]


def test_season_on_one_side_only_still_matches():
    matches, _, _ = match(["Show S01E05.mkv"], ["Show - 05.srt"])
    assert matches[0].subtitle.filename == "Show - 05.srt"


def test_right_season_is_picked():
    matches, _, unmatched_s = match(["Show S02E05.mkv"], ["Show S01E05.srt", "Show S02E05.srt"])
    assert matches[0].subtitle.filename == "Show S02E05.srt"
    assert [s.filename for s in unmatched_s] == ["Show S01E05.srt"]


@pytest.mark.parametrize("extra", [
    "Show - NCOP1.mkv", "Show - NCED 01.mkv", "Show - OP1.mkv", "Show - ED1.mkv",
    "Show - PV1.mkv", "Show - Preview 01.mkv", "Show Menu 1.mkv", "Show NC-OP 1.mkv",
    "Show - Special 1.mkv", "Show OVA - 01.mkv",
])
def test_extras_do_not_take_an_episode_subtitle(extra):
    matches, unmatched_v, unmatched_s = match([extra, "Show - 01.mkv"], ["Show - 01.srt"])
    by_video = {m.video.filename: m for m in matches}
    assert by_video[extra].subtitle is None
    assert by_video["Show - 01.mkv"].subtitle.filename == "Show - 01.srt"
    assert [v.filename for v in unmatched_v] == [extra]
    assert not unmatched_s


def test_extra_subtitle_is_not_given_to_an_episode():
    matches, _, unmatched_s = match(["Show - 01.mkv"], ["Show - NCOP1.srt"])
    assert matches[0].subtitle is None
    assert [s.filename for s in unmatched_s] == ["Show - NCOP1.srt"]


def test_ova_pairs_with_ova_subtitle():
    matches, _, _ = match(["Show OVA - 01.mkv", "Show - 01.mkv"],
                          ["Show - 01.srt", "Show OVA - 01.srt"])
    by_video = {m.video.filename: m.subtitle.filename for m in matches}
    assert by_video == {"Show OVA - 01.mkv": "Show OVA - 01.srt", "Show - 01.mkv": "Show - 01.srt"}


def test_synced_copy_is_preferred_and_original_not_listed():
    matches, unmatched_v, unmatched_s = match(
        ["Show - 01.mkv"], ["Show - 01.srt", "Show - 01.synced.srt"])
    assert matches[0].subtitle.filename == "Show - 01.synced.srt"
    assert matches[0].confidence == MatchConfidence.EXACT
    assert not unmatched_v
    assert not unmatched_s


def test_different_title_still_matches_with_low_score():
    matches, _, _ = match(
        ["[Cleo]Mousou_Dairinin_-_01_(Dual Audio).mkv"],
        ["[Scarlet Team] Paranoia Agent - 01 [BD].ass"])
    m = matches[0]
    assert m.subtitle.filename == "[Scarlet Team] Paranoia Agent - 01 [BD].ass"
    assert m.is_matched
    assert m.score < 50
    assert m.confidence == MatchConfidence.LOW


def test_single_candidate_is_not_blindly_100_percent():
    matches, _, _ = match(["Naruto - 05.mkv"], ["Bleach - 05.srt"])
    assert matches[0].is_matched
    assert matches[0].score < 80
    assert matches[0].confidence in (MatchConfidence.MEDIUM, MatchConfidence.LOW)


def test_same_title_other_group_is_high():
    matches, _, _ = match(["[A] My Show - 05 [1080p].mkv"], ["[B] My Show - 05.ass"])
    assert matches[0].score == 100
    assert matches[0].confidence == MatchConfidence.HIGH


def test_closest_title_wins_between_candidates():
    matches, _, _ = match(["Naruto - 05.mkv", "Bleach - 05.mkv"],
                          ["Bleach - 05.srt", "Naruto - 05.srt"])
    assert {m.video.filename: m.subtitle.filename for m in matches} == {
        "Naruto - 05.mkv": "Naruto - 05.srt", "Bleach - 05.mkv": "Bleach - 05.srt"}


def touch(folder: Path, *names: str):
    for name in names:
        (folder / name).write_bytes(b"x")


def test_scan_ignores_own_outputs_and_pairs_vobsub(tmp_path):
    touch(tmp_path, "Show - 01.mkv", f"Show - 01 {OUTPUT_MARKER}.mkv", "Show - 01.idx",
          "Show - 01.sub", "Show - 02.mp4", "Show - 02.sub", "Show - 03.idx", "notes.txt")
    videos, subs = list_media_files(tmp_path)
    assert [v.name for v in videos] == ["Show - 01.mkv", "Show - 02.mp4"]
    # .idx stands for the VobSub pair; a lone .sub is kept; a lone .idx is unusable
    assert [s.name for s in subs] == ["Show - 01.idx", "Show - 02.sub"]


def test_scan_folder_returns_absolute_paths(tmp_path, monkeypatch):
    touch(tmp_path, "@Show - 01.mkv", "@Show - 01.srt")
    monkeypatch.chdir(tmp_path)
    videos, subs = scan_folder(Path("."))
    assert videos[0].filepath.is_absolute() and subs[0].filepath.is_absolute()
    assert videos[0].filepath == (tmp_path / "@Show - 01.mkv").resolve()


# ── R2-07: extra markers only count next to the number or in a bracket ────────

@pytest.mark.parametrize("name", [
    "Menu Show - 02", "Trailer Park Boys - 02", "Ed Edd n Eddy - 02", "Happy Ending - 01",
    "Opening Night - 01", "Special A - 03", "One Piece - 1000", "Edens Zero - 05",
    "Speed Grapher - 01",
])
def test_marker_words_in_a_title_are_not_extras(name):
    assert info(name + ".mkv").extra_kind == ""
    matches, unmatched_v, unmatched_s = match([name + ".mkv"], [name + ".srt"])
    assert matches[0].subtitle.filename == name + ".srt"
    assert matches[0].confidence == MatchConfidence.EXACT
    assert not unmatched_v and not unmatched_s


@pytest.mark.parametrize("name, kind", [
    ("Show - NCOP1.mkv", "NCOP"), ("[G] Show - OP 01.mkv", "OP"), ("Show - ED2.mkv", "ED"),
    ("[G] Show - 05 [Creditless OP].mkv", "NCOP"), ("[G] Show - 01 [NCOP].mkv", "NCOP"),
    ("Show - 01 (NCED).mkv", "NCED"), ("Show - Preview 03.mkv", "PREVIEW"),
    ("Show - PV1.mkv", "PV"), ("Show - CM 02.mkv", "CM"), ("Show - SP1.mkv", "SPECIAL"),
    ("Show OVA - 01.mkv", "OVA"), ("Show - OP.mkv", "OP"),
])
def test_extra_markers_next_to_the_number_or_in_brackets(name, kind):
    assert info(name).extra_kind == kind


def test_group_tags_are_not_extra_markers():
    for name in ("[Specials] Show - 01.srt", "[PV-Subs] Show - 01.srt"):
        assert info(name).extra_kind == ""
    matches, _, unmatched_s = match(["Show - 01.mkv"], ["[Specials] Show - 01.srt"])
    assert matches[0].subtitle.filename == "[Specials] Show - 01.srt" and not unmatched_s
    matches, _, _ = match(["Show - 01.mkv"], ["[PV-Subs] Show - 01.srt"])
    assert matches[0].subtitle.filename == "[PV-Subs] Show - 01.srt"


def test_extra_pairs_with_the_same_kind_and_number():
    matches, unmatched_v, unmatched_s = match(
        ["Show - NCOP1.mkv", "Show - 01.mkv"], ["Show - 01.srt", "Show - NCOP1.srt"])
    by_video = {m.video.filename: m.subtitle.filename for m in matches}
    assert by_video == {"Show - NCOP1.mkv": "Show - NCOP1.srt", "Show - 01.mkv": "Show - 01.srt"}
    assert not unmatched_v and not unmatched_s
    # Another kind or number does not pair
    matches, _, _ = match(["Show - NCOP1.mkv"], ["Show - NCED1.srt"])
    assert matches[0].subtitle is None
    matches, _, _ = match(["Show - NCOP1.mkv"], ["Show - NCOP2.srt"])
    assert matches[0].subtitle is None


def test_scan_ignores_partial_and_marked_files_of_any_kind(tmp_path):
    touch(tmp_path, "Show - 01.mkv", "Show - 01.srt",
          f"Show - 01 {OUTPUT_MARKER}.mkv.partial.srt",       # old UTF-16 temp copy
          f"Show - 01 {OUTPUT_MARKER}.mkv.partial",
          "Show - 01.mkv.partial", f"Show - 01 {OUTPUT_MARKER}.srt")
    videos, subs = list_media_files(tmp_path)
    assert [v.name for v in videos] == ["Show - 01.mkv"]
    assert [s.name for s in subs] == ["Show - 01.srt"]


# ── R3A-04: a marker after the episode number never steals the episode subtitle ─

@pytest.mark.parametrize("extra, kind", [
    ("Show - 01 Preview.mkv", "PREVIEW"), ("Show - 01 OP.mkv", "OP"), ("Show - 01 NCOP.mkv", "NCOP"),
    ("Show - 05 ED.mkv", "ED"), ("Show - 01 OVA.mkv", "OVA"), ("Show - 01 Special.mkv", "SPECIAL"),
    ("Show - 01 - Preview.mkv", "PREVIEW"), ("Show_01_NCED.mkv", "NCED"), ("Show S01E01 OP.mkv", "OP"),
])
def test_marker_after_the_number_is_an_extra(extra, kind):
    assert info(extra).extra_kind == kind
    episode = "Show - 05.mkv" if "05" in extra else "Show - 01.mkv"
    sub = episode.replace(".mkv", ".srt")
    # The extra sorts first by name: it must still not take the subtitle
    matches, unmatched_v, unmatched_s = match(sorted([extra, episode]), [sub])
    by_video = {m.video.filename: m for m in matches}
    assert by_video[episode].subtitle.filename == sub
    assert by_video[extra].subtitle is None
    assert [v.filename for v in unmatched_v] == [extra] and not unmatched_s
    assert [m.video.filename for m in matches] == sorted([extra, episode])     # order kept


def test_marker_word_ending_a_title_is_still_a_title():
    assert info("Show 2 Opening Night - 01.mkv").extra_kind == ""


def test_plain_video_wins_over_an_unrecognised_marker_video():
    """Backstop: 'Show - 01 [Preview v2].mkv' is not recognised as an extra, but the
    plain episode still gets the plain subtitle."""
    odd = "Show - 01 [Preview v2].mkv"
    assert info(odd).extra_kind == "" and info(odd).episode_num == "1"
    matches, _, _ = match([odd, "Show - 01.mkv"], ["Show - 01.srt"])
    by_video = {m.video.filename: m.subtitle for m in matches}
    assert by_video["Show - 01.mkv"].filename == "Show - 01.srt"
    assert by_video[odd] is None


# ── R3A-05: files without an episode number pair on their name ────────────────

@pytest.mark.parametrize("video, sub", [
    ("Your Name (2016) [1080p].mkv", "Your Name (2016) [1080p].srt"),
    ("Your Name (2016) [1080p].mkv", "Your Name.srt"),
    ("Suzume.mkv", "Suzume.ar.srt"),
    ("Suzume.mkv", "suzume.eng.ass"),
    ("[Group] Suzume [BD 1080p x265 FLAC].mkv", "Suzume.ara.srt"),
    ("Show The Movie.mkv", "Show The Movie.srt"),
    ("Show - ED.mkv", "Show - ED.srt"),
    ("Show OVA.mkv", "Show OVA.srt"),
])
def test_numberless_files_pair_on_their_name(video, sub):
    matches, unmatched_v, unmatched_s = match([video], [sub])
    assert matches[0].subtitle is not None and matches[0].subtitle.filename == sub
    assert not unmatched_v and not unmatched_s


def test_numberless_files_with_other_names_do_not_pair():
    matches, _, unmatched_s = match(["Suzume.mkv"], ["Weathering With You.srt"])
    assert matches[0].subtitle is None and len(unmatched_s) == 1
    # kind must agree too
    matches, _, _ = match(["Show - ED.mkv"], ["Show - OP.srt"])
    assert matches[0].subtitle is None


def test_numbered_episode_never_takes_a_numberless_subtitle():
    matches, _, unmatched_s = match(["Show - 01.mkv"], ["Show.srt"])
    assert matches[0].subtitle is None and [s.filename for s in unmatched_s] == ["Show.srt"]
    matches, _, unmatched_s = match(["Show.mkv"], ["Show - 01.srt"])
    assert matches[0].subtitle is None and [s.filename for s in unmatched_s] == ["Show - 01.srt"]


def test_movie_folder_merges_end_to_end(tmp_path):
    """A single film plus its subtitle goes all the way through the engine."""
    from core.engine import ProcessingEngine
    from core.models import AppConfig, FileInfo, ProcessingOptions, ProcessingResult, ProcessingStatus

    (tmp_path / "Your Name (2016) [1080p].mkv").write_bytes(b"video")
    (tmp_path / "Your Name (2016) [1080p].srt").write_bytes(
        b"1\r\n00:00:01,000 --> 00:00:02,000\r\nHello\r\n")
    merged = []

    class Tools:
        def identify(self, path, cancel_event=None):
            return FileInfo(filepath=Path(path))

        def merge(self, **kwargs):
            merged.append(kwargs)
            Path(kwargs["output_path"]).write_bytes(b"out")
            return ProcessingResult(status=ProcessingStatus.COMPLETED)

        def terminate_all(self):
            pass

    engine = ProcessingEngine(AppConfig(), mkv_tools=Tools())
    scan = engine.scan_and_match(tmp_path)
    assert scan.matches[0].is_matched and not scan.unmatched_subtitles
    result = engine.process_batch(scan, ProcessingOptions())
    assert result.successful == 1
    assert Path(merged[0]["subtitle_path"]).name == "Your Name (2016) [1080p].srt"
    assert (tmp_path / "PROCESSED" / "Your Name (2016) [1080p].mkv").is_file()


# ── R3A-07 / R3A-08 ───────────────────────────────────────────────────────────

def test_crc_bracket_is_not_an_ending():
    for name in ("[G] Show - 05 [ED921796].mkv", "[G] Show - 05 [OP123456].mkv",
                 "[G] Show - 05 [ABCDEF12].mkv"):
        assert info(name).extra_kind == "" and info(name).episode_num == "5"
    matches, _, _ = match(["[G] Show - 05 [ED921796].mkv"], ["[G] Show - 05.srt"])
    assert matches[0].subtitle.filename == "[G] Show - 05.srt"
    assert info("[G] Show - 05 [ED 1234].mkv").extra_kind == ""   # 4 digits: not a marker number
    assert info("[G] Show - 05 [ED 2].mkv").extra_kind == "ED"


def test_higher_subtitle_version_wins():
    assert info("Show - 01v2.srt").version == 2 and info("Show - 01.srt").version == 1
    for subs in (["Show - 01.srt", "Show - 01v2.srt"], ["Show - 01v2.srt", "Show - 01.srt"]):
        matches, _, unmatched_s = match(["Show - 01.mkv"], subs)
        assert matches[0].subtitle.filename == "Show - 01v2.srt"
        assert [s.filename for s in unmatched_s] == ["Show - 01.srt"]


# ── R3B-06: extras are labelled by kind and number ────────────────────────────

@pytest.mark.parametrize("name, label", [
    ("Show - NCOP1.mkv", "NCOP 1"), ("Show - 05.mkv", "5"), ("Show - ED.mkv", "ED"),
    ("Show - 01 Preview.mkv", "PREVIEW 1"), ("Suzume.mkv", "?"),
])
def test_episode_label(name, label):
    assert info(name).label == label
