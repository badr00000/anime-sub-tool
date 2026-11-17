"""Processor and batch logic with a fake mkvmerge wrapper (no real binary)."""

import threading
from pathlib import Path

import pytest

from conftest import SRT_TEXT, write_srt
from core.batch import BatchProcessor
from core.constants import OUTPUT_MARKER
from core.engine import ProcessingEngine
from core.matcher import match_files, scan_folder
from core.models import (
    AppConfig, FileInfo, ProcessingOptions, ProcessingResult, ProcessingStatus as S, Track, TrackType,
)
from core.processor import EpisodeProcessor

TRACKS = [
    Track(id=0, type=TrackType.VIDEO),
    Track(id=1, type=TrackType.AUDIO, language="jpn"),
    Track(id=2, type=TrackType.AUDIO, language="eng"),
    Track(id=3, type=TrackType.SUBTITLE, language="eng"),
    Track(id=4, type=TrackType.SUBTITLE, language="und"),
    Track(id=5, type=TrackType.SUBTITLE, language="fre"),
]


class FakeMKV:
    def __init__(self, tracks=TRACKS, status=S.COMPLETED, identify_error=""):
        self.tracks = tracks
        self.status = status
        self.identify_error = identify_error
        self.calls = []
        self.terminated = False
        self.started = threading.Event()
        self.release = threading.Event()
        self.release.set()

    def identify(self, path):
        return FileInfo(filepath=Path(path), tracks=list(self.tracks), error=self.identify_error)

    def merge(self, **kwargs):
        self.calls.append(kwargs)
        self.started.set()
        self.release.wait(10)
        if self.status in (S.COMPLETED, S.COMPLETED_WITH_WARNINGS):
            Path(kwargs["output_path"]).write_bytes(b"MKV")
        elif self.status == S.FAILED:
            Path(kwargs["output_path"]).write_bytes(b"half")     # a broken partial file
        return ProcessingResult(status=self.status, output_path=Path(kwargs["output_path"]),
                                message="Error: boom" if self.status == S.FAILED else "ok")

    def terminate_all(self):
        self.terminated = True


@pytest.fixture
def season(tmp_path):
    for n in (1, 2, 3):
        (tmp_path / f"Show - {n:02d}.mkv").write_bytes(b"video")
        write_srt(tmp_path / f"Show - {n:02d}.srt")
    return tmp_path


def matches_of(folder):
    videos, subs = scan_folder(folder)
    return match_files(videos, subs)[0]


def run_one(folder, options=None, fake=None, index=0):
    fake = fake or FakeMKV()
    processor = EpisodeProcessor(fake, options or ProcessingOptions())
    return processor.process(matches_of(folder)[index]), fake


def test_audio_and_subtitle_selection(season):
    result, fake = run_one(season)
    assert result.status == S.COMPLETED
    call = fake.calls[0]
    assert call["audio_track_ids"] == [1]            # jpn only
    assert call["sub_track_ids"] == []               # remove all originals
    assert call["subtitle_path"] == str(season / "Show - 01.srt")
    assert (call["sub_language"], call["sub_name"], call["sub_default"]) == ("ara", "Arabic", True)
    assert call["sub_charset"] is None
    assert result.output_path == season / "PROCESSED" / "Show - 01.mkv"
    assert result.output_path.read_bytes() == b"MKV"
    assert not list((season / "PROCESSED").glob("*.partial"))


@pytest.mark.parametrize("changes, audio, subs", [
    (dict(keep_audio_langs=[]), None, []),                           # no filter = keep all audio
    (dict(keep_audio_langs=["ger"]), None, []),                      # language absent = keep all
    (dict(keep_audio_langs=["ja", "en"]), [1, 2], []),               # 2-letter codes
    (dict(remove_existing_subs=False), [1], None),                   # keep every original sub
    (dict(keep_sub_langs=["fra"]), [1], [5]),                        # fra == fre
    (dict(edit_target_lang="und"), [1], [4]),                        # edited track is kept
    (dict(edit_target_lang="und", isolate_edited_track=True, remove_existing_subs=False), [1], [4]),
])
def test_track_filters(season, changes, audio, subs):
    result, fake = run_one(season, ProcessingOptions(**changes))
    assert fake.calls[0]["audio_track_ids"] == audio
    assert fake.calls[0]["sub_track_ids"] == subs
    if "edit_target_lang" in changes:
        assert fake.calls[0]["edit_track_id"] == 4


def test_unmatched_episode_is_skipped_by_default(season):
    (season / "Show - 01.srt").unlink()
    result, fake = run_one(season)
    assert result.status == S.SKIPPED and "No matching subtitle" in result.message
    assert fake.calls == []
    assert not (season / "PROCESSED").exists()

    result, fake = run_one(season, ProcessingOptions(process_unmatched=True))
    assert result.status == S.COMPLETED
    assert fake.calls[0]["subtitle_path"] is None


def test_existing_output_is_skipped_unless_overwrite(season):
    out = season / "PROCESSED" / "Show - 01.mkv"
    out.parent.mkdir()
    out.write_bytes(b"precious")

    result, fake = run_one(season)
    assert result.status == S.SKIPPED and "already exists" in result.message
    assert fake.calls == [] and out.read_bytes() == b"precious"

    result, fake = run_one(season, ProcessingOptions(overwrite_existing=True))
    assert result.status == S.COMPLETED and out.read_bytes() == b"MKV"


def test_failed_merge_leaves_no_output_and_keeps_existing_one(season):
    out = season / "PROCESSED" / "Show - 01.mkv"
    result, _ = run_one(season, fake=FakeMKV(status=S.FAILED))
    assert result.status == S.FAILED
    assert not out.exists() and not list(out.parent.glob("*.partial"))

    out.write_bytes(b"precious")
    result, _ = run_one(season, ProcessingOptions(overwrite_existing=True), FakeMKV(status=S.FAILED))
    assert result.status == S.FAILED and out.read_bytes() == b"precious"


def test_outputs_are_always_mkv(tmp_path):
    for ext in (".mp4", ".avi"):
        (tmp_path / f"Show - 01{ext}").write_bytes(b"v")
        write_srt(tmp_path / "Show - 01.srt")
        result, _ = run_one(tmp_path)
        assert result.output_path.name == "Show - 01.mkv"
        (tmp_path / f"Show - 01{ext}").unlink()
        result.output_path.unlink()


def test_same_folder_output_gets_marker_and_is_not_rescanned(season):
    options = ProcessingOptions(create_output_folder=False)
    result, _ = run_one(season, options)
    assert result.output_path == season / f"Show - 01 {OUTPUT_MARKER}.mkv"
    assert result.output_path.exists()
    assert (season / "Show - 01.mkv").read_bytes() == b"video"       # source untouched
    # Next scan: the output is not an episode, so nothing can overwrite it
    assert [m.video.filename for m in matches_of(season)] == [
        "Show - 01.mkv", "Show - 02.mkv", "Show - 03.mkv"]
    result2, fake2 = run_one(season, options)
    assert result2.status == S.SKIPPED and fake2.calls == []


def test_explicit_output_dir(season, tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("elsewhere") / "deep" / "out"
    result, _ = run_one(season, ProcessingOptions(output_dir=out_dir))
    assert result.output_path == out_dir / "Show - 01.mkv" and result.output_path.exists()


def test_never_writes_onto_an_input_of_the_batch(tmp_path):
    # 'Show - 01.mp4' wants to write 'Show - 01.mkv' -- which is another episode of the batch
    out_dir = tmp_path / "PROCESSED"
    out_dir.mkdir()
    (tmp_path / "Show - 01.mp4").write_bytes(b"a")
    write_srt(tmp_path / "Show - 01.srt")
    victim = out_dir / "Show - 01.mkv"
    victim.write_bytes(b"input")
    fake = FakeMKV()
    processor = EpisodeProcessor(fake, ProcessingOptions(overwrite_existing=True),
                                 protected_paths=[victim])
    result = processor.process(matches_of(tmp_path)[0])
    assert result.status == S.FAILED and "input" in result.message
    assert fake.calls == [] and victim.read_bytes() == b"input"


def test_two_episodes_with_the_same_output_name(tmp_path):
    (tmp_path / "Show - 01.mp4").write_bytes(b"a")
    (tmp_path / "Show - 01.mkv").write_bytes(b"b")
    write_srt(tmp_path / "Show - 01.srt")
    fake = FakeMKV()
    options = ProcessingOptions(process_unmatched=True)
    batch = BatchProcessor(EpisodeProcessor(fake, options), max_workers=2)
    result = batch.process_all(matches_of(tmp_path), options)
    assert (result.successful, result.failed) == (1, 1)
    assert "same output file" in [r for r in result.results if r.status == S.FAILED][0].message


def test_empty_subtitle_fails_the_episode(season):
    (season / "Show - 01.srt").write_bytes(b"")
    result, fake = run_one(season)
    assert result.status == S.FAILED and "no subtitle lines" in result.message
    assert fake.calls == []
    (season / "Show - 01.srt").write_bytes(b"1\n\nnot a cue\n")
    assert run_one(season)[0].status == S.FAILED


def test_negative_offset_warns_per_episode(season):
    result, fake = run_one(season, ProcessingOptions(subtitle_offset_ms=-1500))
    assert result.status == S.COMPLETED
    assert fake.calls[0]["sub_offset_ms"] == -1500
    assert len(result.warnings) == 1 and "1 of 2 line(s) start before 0:00" in result.warnings[0]
    assert run_one(season, ProcessingOptions(subtitle_offset_ms=500))[0].warnings == []


def test_identify_failure_fails_the_episode(season):
    result, fake = run_one(season, fake=FakeMKV(identify_error="mkvmerge could not be started (X:/m.exe)"))
    assert result.status == S.FAILED and "could not be started" in result.message
    assert fake.calls == []


def test_charset_is_detected_and_passed(season):
    arabic = SRT_TEXT.replace("Hello", "مرحبا بكم في هذا العالم").replace("World", "إلى اللقاء يا صديقي")
    write_srt(season / "Show - 01.srt", arabic, "cp1256")
    result, fake = run_one(season)
    assert fake.calls[0]["sub_charset"] == "cp1256"


def run_batch(folder, options, fake=None, workers=2, logs=None):
    fake = fake or FakeMKV()
    batch = BatchProcessor(EpisodeProcessor(fake, options), max_workers=workers)
    log = (lambda msg, lvl="INFO": logs.append((lvl, msg))) if logs is not None else None
    return batch.process_all(matches_of(folder), options, log_callback=log), fake


def test_batch_counts_skipped_separately(season):
    (season / "Show - 02.srt").unlink()                        # unmatched -> skipped
    (season / "PROCESSED").mkdir()
    (season / "PROCESSED" / "Show - 03.mkv").write_bytes(b"old")   # exists -> skipped
    logs = []
    result, fake = run_batch(season, ProcessingOptions(), logs=logs)
    assert (result.total, result.successful, result.skipped, result.failed, result.cancelled) == (3, 1, 2, 0, 0)
    assert [r.status for r in result.results] == [S.COMPLETED, S.SKIPPED, S.SKIPPED]
    assert [r.video_name for r in result.results] == ["Show - 01.mkv", "Show - 02.mkv", "Show - 03.mkv"]
    assert len(fake.calls) == 1
    skipped_logs = [m for lvl, m in logs if lvl == "WARNING" and m.startswith("Skipped episode")]
    assert len(skipped_logs) == 2


def test_dry_run_writes_nothing(season):
    (season / "Show - 02.srt").unlink()
    before = sorted(p.name for p in season.rglob("*"))
    logs = []
    result, fake = run_batch(season, ProcessingOptions(dry_run=True), logs=logs)
    assert result.dry_run is True
    assert (result.successful, result.skipped) == (2, 1)
    assert fake.calls == []
    assert sorted(p.name for p in season.rglob("*")) == before
    assert any("[DRY RUN]" in m for _, m in logs)


def test_cancel_stops_remaining_episodes(season):
    fake = FakeMKV()
    fake.release.clear()
    options = ProcessingOptions()
    batch = BatchProcessor(EpisodeProcessor(fake, options), max_workers=1)
    holder = {}
    thread = threading.Thread(
        target=lambda: holder.setdefault("result", batch.process_all(matches_of(season), options)))
    thread.start()
    assert fake.started.wait(10)            # episode 1 is inside mkvmerge
    batch.cancel()
    fake.release.set()
    thread.join(10)
    result = holder["result"]
    assert (result.successful, result.cancelled, result.failed) == (1, 2, 0)
    assert len(fake.calls) == 1 and fake.terminated is False
    batch.cancel(force=True)
    assert fake.terminated is True


def test_engine_uses_config_and_reports_output_dir(season):
    config = AppConfig(default_workers=3, output_subfolder="DONE", subtitle_language="eng",
                       subtitle_name="English")
    fake = FakeMKV()
    engine = ProcessingEngine(config, mkv_tools=fake)
    options = engine.default_options()
    scan = engine.scan_and_match(season)
    assert scan.folder_path == season.resolve()
    assert scan.matches[0].subtitle.encoding == "UTF-8"
    assert engine.output_dir(scan, options) == season / "DONE"
    result = engine.process_batch(scan, options)
    assert result.successful == 3
    assert (season / "DONE" / "Show - 02.mkv").exists()
    assert fake.calls[0]["sub_language"] == "eng" and fake.calls[0]["sub_name"] == "English"

    preview = engine.generate_preview(scan, options)
    assert [op.action for op in preview.episodes[0].operations] == ["Skip"]   # output exists now


def test_worker_count_is_clamped():
    assert BatchProcessor(EpisodeProcessor(FakeMKV(), ProcessingOptions()), max_workers=0).max_workers == 1
    assert BatchProcessor(EpisodeProcessor(FakeMKV(), ProcessingOptions()), max_workers=99).max_workers == 8
