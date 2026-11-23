"""Round 3 low findings: CLI track filters (R3B-02), offsets that leave nothing
(R3B-03), one offset limit everywhere (R3B-05), extra labels and the 'Starting'
log line (R3B-06), keeping an unreadable config (R3B-07)."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from conftest import SRT_TEXT, write_srt
from core.batch import BatchProcessor
from core.constants import MAX_OFFSET_MS
from core.engine import ProcessingEngine
from core.models import (
    AppConfig, FileInfo, ProcessingOptions, ProcessingResult, ProcessingStatus as S, Track, TrackType,
)
from core.processor import EpisodeProcessor


class Tools:
    """Minimal stand-in for MKVToolsWrapper."""

    def __init__(self):
        self.calls = []

    def identify(self, path, cancel_event=None):
        return FileInfo(filepath=Path(path), tracks=[
            Track(id=0, type=TrackType.VIDEO), Track(id=1, type=TrackType.AUDIO, language="jpn"),
            Track(id=2, type=TrackType.AUDIO, language="eng"),
            Track(id=3, type=TrackType.SUBTITLE, language="eng")])

    def merge(self, cancel_event=None, **kwargs):
        self.calls.append(kwargs)
        Path(kwargs["output_path"]).write_bytes(b"MKV")
        return ProcessingResult(status=S.COMPLETED)

    def terminate_all(self):
        pass


@pytest.fixture
def cli(monkeypatch):
    import cli.commands as commands
    monkeypatch.setattr(commands, "setup_logging", lambda **kw: None)
    return commands


def folder_with(tmp_path, *names):
    for name in names:
        if name.endswith(".srt"):
            write_srt(tmp_path / name)
        else:
            (tmp_path / name).write_bytes(b"video")
    return tmp_path


# ── R3B-02: --keep-audio / --keep-subs ────────────────────────────────────────

@pytest.mark.parametrize("args, audio, subs", [
    ([], ["jpn"], []),                                         # documented defaults
    (["--keep-audio", "ja,EN"], ["jpn", "eng"], []),
    (["--keep-audio", "all"], [], []),                         # every audio track
    (["--keep-audio", ""], [], []),
    (["--keep-audio", "ja-JP, jpn"], ["jpn"], []),
    (["--keep-subs", "en,fra"], ["jpn"], ["eng", "fre"]),
])
def test_cli_track_filters_reach_the_options(cli, tmp_path, monkeypatch, args, audio, subs):
    folder_with(tmp_path, "Show - 01.mkv", "Show - 01.srt")
    seen = {}
    monkeypatch.setattr(cli, "validate_mkvtoolnix", lambda tools: "mkvmerge v100")
    monkeypatch.setattr(ProcessingEngine, "process_batch",
                        lambda self, scan, opts, *a: seen.setdefault("opts", opts) and
                        __import__("core.models", fromlist=["BatchResult"]).BatchResult())
    result = CliRunner().invoke(cli.cli, ["process", str(tmp_path), "-y", *args])
    assert result.exit_code == 0, result.output
    assert seen["opts"].keep_audio_langs == audio
    assert seen["opts"].keep_sub_langs == subs


def test_cli_track_filters_in_preview_and_help(cli, tmp_path):
    folder_with(tmp_path, "Show - 01.mkv", "Show - 01.srt")
    runner = CliRunner()
    out = runner.invoke(cli.cli, ["preview", str(tmp_path), "--keep-audio", "all",
                                  "--keep-subs", "eng"]).output
    assert "Keep all audio" in out and "except eng" in out
    help_text = runner.invoke(cli.cli, ["process", "--help"]).output
    assert "--keep-audio" in help_text and "--keep-subs" in help_text
    assert "Default: jpn" in " ".join(help_text.split())
    bad = runner.invoke(cli.cli, ["preview", str(tmp_path), "--keep-audio", "jpn;rm -rf"])
    assert bad.exit_code != 0 and "not a language code" in bad.output


def test_readme_documents_the_track_filter_defaults():
    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
    assert "--keep-audio" in readme and "--keep-subs" in readme and "Japanese audio" in readme


# ── R3B-03: an offset that leaves nothing is an error ─────────────────────────

def test_merge_fails_when_every_line_ends_before_zero(tmp_path):
    folder_with(tmp_path, "Show - 01.mkv", "Show - 01.srt")
    tools = Tools()
    engine = ProcessingEngine(AppConfig(), mkv_tools=tools)
    scan = engine.scan_and_match(tmp_path)
    result = engine.process_batch(scan, ProcessingOptions(subtitle_offset_ms=-4500))  # last ends 4.5 s
    assert (result.successful, result.failed) == (0, 1)
    assert "every line" in result.results[0].message and tools.calls == []
    dry = engine.process_batch(scan, ProcessingOptions(subtitle_offset_ms=-6000, dry_run=True))
    assert dry.failed == 1
    # One line left: still merged, with the usual warning
    ok = engine.process_batch(scan, ProcessingOptions(subtitle_offset_ms=-4000))
    assert ok.successful == 1 and tools.calls


def test_shift_refuses_an_offset_that_leaves_nothing(cli, tmp_path):
    src = write_srt(tmp_path / "a.srt")
    result = CliRunner().invoke(cli.cli, ["shift", str(src), "--offset", "-5"])
    assert result.exit_code == 1 and "every line" in result.output
    assert not (tmp_path / "a.synced.srt").exists()
    assert CliRunner().invoke(cli.cli, ["shift", str(src), "--offset", "-4"]).exit_code == 0


def test_sync_tool_refuses_to_save_an_empty_result(qapp, dialogs_stub, tmp_path):
    from gui.widgets.sync_page import SyncPage
    page = SyncPage()
    try:
        page.load_subtitle(str(write_srt(tmp_path / "a.srt")))
        page.set_offset(-5000)
        page.save()
        assert not (tmp_path / "a.synced.srt").exists()
        assert dialogs_stub[-1][0] == "warn" and "every line" in dialogs_stub[-1][2]
        page.set_offset(-4000)
        page.save()
        assert (tmp_path / "a.synced.srt").exists()
    finally:
        page.shutdown()


@pytest.fixture
def dialogs_stub(monkeypatch):
    from gui.dialogs import messages
    shown = []
    for kind in ("info", "warn", "error"):
        monkeypatch.setattr(messages, kind,
                            lambda parent, title, text, kind=kind: shown.append((kind, title, text)))
    monkeypatch.setattr(messages, "confirm", lambda *a: True)
    return shown


# ── R3B-05: one offset limit ──────────────────────────────────────────────────

def test_gui_offset_limit_matches_cli_and_config(qapp, cli):
    from core.config import _MAX_OFFSET_MS, clean_preset
    from gui.widgets.options_panel import OptionsPanel
    from gui.widgets.sync_page import SyncPage
    assert _MAX_OFFSET_MS == MAX_OFFSET_MS and cli._MAX_OFFSET_SECONDS * 1000 == MAX_OFFSET_MS
    config = AppConfig(presets={"late": {"subtitle_offset_ms": 1_800_000}})
    panel = OptionsPanel(config)
    assert panel.offset_spin.maximum() * 1000 == MAX_OFFSET_MS
    assert panel.offset_spin.minimum() * 1000 == -MAX_OFFSET_MS
    panel._load_preset("late")
    assert panel.get_options().subtitle_offset_ms == 1_800_000           # not clamped to 600 s
    assert clean_preset({"subtitle_offset_ms": MAX_OFFSET_MS}) == {"subtitle_offset_ms": MAX_OFFSET_MS}
    page = SyncPage()
    try:
        assert page.exact.maximum() * 1000 == MAX_OFFSET_MS
    finally:
        page.shutdown()


# ── R3B-06: extras are named by kind; 'Starting' only for real work ───────────

def test_logs_name_extras_and_skip_starting_for_skipped(tmp_path):
    folder_with(tmp_path, "Show - 01.mkv", "Show - 01.srt", "Show - NCOP1.mkv", "Show - NCOP1.srt",
                "Show - 02.mkv")                                      # 02: no subtitle -> skipped
    tools = Tools()
    engine = ProcessingEngine(AppConfig(), mkv_tools=tools)
    scan = engine.scan_and_match(tmp_path)
    assert sorted(m.video.label for m in scan.matches) == ["1", "2", "NCOP 1"]
    logs = []
    progress = []
    result = engine.process_batch(scan, ProcessingOptions(), lambda ep, p, o: progress.append(ep),
                                  lambda msg, lvl: logs.append(msg))
    assert (result.successful, result.skipped) == (2, 1)
    assert "Starting processing for episode NCOP 1" in logs
    assert "Completed processing for episode NCOP 1" in logs
    assert "Starting processing for episode 1" in logs
    assert not any("Starting" in m and "episode 2" in m for m in logs)
    assert any(m.startswith("Skipped episode 2") for m in logs)
    assert "NCOP 1" in progress

    preview = engine.generate_preview(scan, ProcessingOptions())
    assert sorted(e.episode_num for e in preview.episodes) == ["1", "2", "NCOP 1"]


def test_starting_not_logged_when_the_subtitle_check_fails(tmp_path):
    folder_with(tmp_path, "Show - 01.mkv")
    (tmp_path / "Show - 01.srt").write_bytes(b"")
    logs = []
    engine = ProcessingEngine(AppConfig(), mkv_tools=Tools())
    result = engine.process_batch(engine.scan_and_match(tmp_path), ProcessingOptions(),
                                  None, lambda msg, lvl: logs.append(msg))
    assert result.failed == 1 and not any("Starting" in m for m in logs)


def test_cli_scan_and_preview_show_the_extra_kind(cli, tmp_path):
    folder_with(tmp_path, "Show - 01.mkv", "Show - NCOP1.mkv", "Show - NCOP1.srt")
    runner = CliRunner()
    scan = runner.invoke(cli.cli, ["scan", str(tmp_path)]).output
    assert "NCOP 1" in scan
    preview = runner.invoke(cli.cli, ["preview", str(tmp_path)]).output
    assert "Episode NCOP 1" in preview


def test_gui_preview_table_shows_the_extra_kind(qapp, tmp_path):
    from gui.widgets.preview_panel import PreviewPanel
    folder_with(tmp_path, "Show - 01.mkv", "Show - NCOP1.mkv", "Show - NCOP1.srt")
    scan = ProcessingEngine(AppConfig(), mkv_tools=Tools()).scan_and_match(tmp_path)
    panel = PreviewPanel()
    panel.populate(scan)
    labels = {panel.table.item(r, 0).text() for r in range(panel.table.rowCount())}
    assert labels == {"EP 01", "NCOP 1"}


# ── R3B-07: an unreadable config is kept before it is overwritten ─────────────

def test_unreadable_config_is_kept_as_bad_before_saving(isolated_home):
    from core import config as cfg
    path = cfg._get_config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    broken = b'{"presets": {"Mine": {"workers": 2}},'          # truncated JSON
    path.write_bytes(broken)
    config = cfg.load_config()
    assert config == AppConfig()
    assert path.read_bytes() == broken                          # loading changes nothing
    config.subtitle_name = "New"
    assert cfg.save_config(config)
    assert (path.parent / "config.json.bad").read_bytes() == broken
    assert json.loads(path.read_text(encoding="utf-8"))["subtitle_name"] == "New"
    # The next save does not touch the backup again
    assert cfg.save_config(config)
    assert sorted(p.name for p in path.parent.glob("config.json.bad*")) == ["config.json.bad"]

    # A second broken file later gets a numbered backup; the first one is kept
    path.write_bytes(b"\xff\xfe garbage")
    cfg.load_config()
    cfg.save_config(config)
    assert (path.parent / "config.json.bad").read_bytes() == broken
    assert (path.parent / "config.json.bad.2").read_bytes() == b"\xff\xfe garbage"


def test_readable_config_is_never_moved(isolated_home):
    from core import config as cfg
    cfg.save_config(AppConfig(subtitle_name="A"))
    cfg.load_config()
    cfg.save_config(AppConfig(subtitle_name="B"))
    assert not list(cfg._get_config_file().parent.glob("*.bad*"))
