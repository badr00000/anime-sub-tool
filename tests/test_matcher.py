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
