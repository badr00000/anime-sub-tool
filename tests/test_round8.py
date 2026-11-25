"""Episodes with no subtitle file are still cleaned when the user keeps some of
the subtitles already inside (keep only the Arabic track) or fixes a track."""

import pytest

from core.models import ProcessingOptions, ProcessingStatus as S, Track, TrackType
from test_processor_batch import FakeMKV, run_one

ARABIC_INSIDE = [
    Track(id=0, type=TrackType.VIDEO),
    Track(id=1, type=TrackType.AUDIO, language="jpn"),
    Track(id=2, type=TrackType.SUBTITLE, language="eng"),
    Track(id=3, type=TrackType.SUBTITLE, language="fre"),
    Track(id=4, type=TrackType.SUBTITLE, language="ara"),
    Track(id=5, type=TrackType.SUBTITLE, language="rus"),
]


@pytest.fixture
def bare_season(tmp_path):
    for n in (1, 2):
        (tmp_path / f"Show - {n:02d}.mkv").write_bytes(b"video")
    return tmp_path


def test_keep_only_arabic_inside_without_subtitle_files(bare_season):
    options = ProcessingOptions(keep_sub_langs=["ara"])
    result, fake = run_one(bare_season, options, FakeMKV(tracks=ARABIC_INSIDE))
    assert result.status == S.COMPLETED
    call = fake.calls[0]
    assert call["subtitle_path"] is None
    assert call["sub_track_ids"] == [4]
    assert call["default_track_id"] == 4
    assert call["clear_default_track_ids"] == []


def test_kept_arabic_becomes_default_over_kept_english(bare_season):
    options = ProcessingOptions(keep_sub_langs=["ara", "eng"])
    result, fake = run_one(bare_season, options, FakeMKV(tracks=ARABIC_INSIDE))
    call = fake.calls[0]
    assert call["sub_track_ids"] == [2, 4]
    assert call["default_track_id"] == 4
    assert call["clear_default_track_ids"] == [2]


def test_no_default_change_when_wanted_language_is_not_kept(bare_season):
    options = ProcessingOptions(keep_sub_langs=["eng"])
    result, fake = run_one(bare_season, options, FakeMKV(tracks=ARABIC_INSIDE))
    call = fake.calls[0]
    assert call["default_track_id"] is None and call["clear_default_track_ids"] == []


def test_fixing_a_track_without_subtitle_files(bare_season):
    options = ProcessingOptions(edit_target_lang="und", edit_new_lang="ara")
    result, fake = run_one(bare_season, options, FakeMKV(tracks=ARABIC_INSIDE))
    assert result.status == S.COMPLETED


def test_plain_cleanup_still_skips_episodes_without_subtitle(bare_season):
    result, fake = run_one(bare_season, ProcessingOptions(), FakeMKV(tracks=ARABIC_INSIDE))
    assert result.status == S.SKIPPED and fake.calls == []


def test_keep_list_ignored_when_existing_subtitles_are_kept(bare_season):
    options = ProcessingOptions(keep_sub_langs=["ara"], remove_existing_subs=False)
    result, fake = run_one(bare_season, options, FakeMKV(tracks=ARABIC_INSIDE))
    assert result.status == S.SKIPPED


def test_options_flag():
    assert not ProcessingOptions().cleans_without_subtitle
    assert ProcessingOptions(process_unmatched=True).cleans_without_subtitle
    assert ProcessingOptions(keep_sub_langs=["ara"]).cleans_without_subtitle
    assert ProcessingOptions(edit_target_lang="eng").cleans_without_subtitle
