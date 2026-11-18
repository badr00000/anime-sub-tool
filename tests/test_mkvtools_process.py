"""MKVToolsWrapper process handling with a fake Popen (no real binary).

The fake behaves like mkvmerge on Windows: Popen.terminate() ends the process
with exit code 1, the same code mkvmerge uses for "finished with warnings".
"""

import io
import json
import threading
from pathlib import Path

import pytest

import core.mkvtools as mkvtools
from conftest import write_srt
from core.batch import BatchProcessor
from core.constants import MKVMERGE_WARNING
from core.matcher import match_files, scan_folder
from core.mkvtools import MKVToolsWrapper
from core.models import ProcessingOptions, ProcessingStatus as S
from core.processor import EpisodeProcessor

IDENTIFY_JSON = json.dumps({
    "container": {"recognized": True, "supported": True},
    "tracks": [{"id": 0, "type": "video", "codec": "AVC", "properties": {}},
               {"id": 1, "type": "audio", "codec": "AAC", "properties": {"language": "jpn"}}],
})


class _Stdout:
    """Pipe of the fake process: the given lines, then blocks until the process ends."""

    def __init__(self, process, lines):
        self._process = process
        self._lines = list(lines)

    def readline(self):
        if self._lines:
            return self._lines.pop(0)
        self._process.done.wait(10)
        return ""

    def close(self):
        pass


class FakePopen:
    instances: list["FakePopen"] = []
    # Set by a test: merges block after their first progress line until released
    hold_merge = True
    hold_identify = False
    started_any = threading.Event()

    def __init__(self, cmd, stdout=None, stderr=None, **kwargs):
        self.cmd = cmd
        self.returncode = None
        self.done = threading.Event()
        self.running = threading.Event()
        self.is_identify = "-J" in cmd
        FakePopen.instances.append(self)
        if self.is_identify:
            self.stdout = io.StringIO(IDENTIFY_JSON)
            if not FakePopen.hold_identify:
                self._exit(0)
        else:
            output = Path(cmd[cmd.index("-o") + 1])
            output.write_bytes(b"x" * 1000)          # mkvmerge has started writing
            self.stdout = _Stdout(self, ["The file has been opened for writing.\n", "Progress: 5%\n"])
            if not FakePopen.hold_merge:
                output.write_bytes(b"x" * 5000)
                self.stdout = _Stdout(self, ["Progress: 100%\n"])
                self._exit(0)
        self.running.set()
        FakePopen.started_any.set()

    def _exit(self, code):
        if self.returncode is None:
            self.returncode = code
        self.done.set()

    def communicate(self):
        self.done.wait(10)
        return (IDENTIFY_JSON if self.returncode == 0 else ""), ""

    def wait(self, timeout=None):
        self.done.wait(10)
        return self.returncode

    def terminate(self):
        self._exit(1)          # TerminateProcess(handle, 1), as subprocess does on Windows

    kill = terminate


@pytest.fixture
def fake_popen(monkeypatch):
    FakePopen.instances = []
    FakePopen.hold_merge = True
    FakePopen.hold_identify = False
    FakePopen.started_any = threading.Event()
    monkeypatch.setattr(mkvtools.subprocess, "Popen", FakePopen)
    return FakePopen


def merges(fake):
    return [p for p in fake.instances if not p.is_identify]


def test_killed_merge_is_cancelled_even_with_exit_code_1(tmp_path, fake_popen):
    """R2-01: exit code 1 after terminate() must never read as 'completed with warnings'."""
    tools = MKVToolsWrapper("")
    holder = {}
    progress = threading.Event()
    thread = threading.Thread(target=lambda: holder.setdefault("result", tools.merge(
        str(tmp_path / "in.mkv"), str(tmp_path / "out.mkv.partial"),
        progress_callback=lambda pct: progress.set())))
    thread.start()
    assert progress.wait(10)                 # mkvmerge is mid-write
    tools.terminate_all()
    thread.join(10)
    assert merges(fake_popen)[0].returncode == MKVMERGE_WARNING
    assert holder["result"].status == S.CANCELLED


def test_nothing_starts_after_terminate_all(tmp_path, fake_popen):
    tools = MKVToolsWrapper("")
    tools.terminate_all()
    assert tools.merge(str(tmp_path / "a.mkv"), str(tmp_path / "b.mkv")).status == S.CANCELLED
    info = tools.identify(str(tmp_path / "a.mkv"))
    assert info.cancelled and info.error
    assert fake_popen.instances == []


def test_cancel_event_stops_a_start(tmp_path, fake_popen):
    tools = MKVToolsWrapper("")
    event = threading.Event()
    event.set()
    assert tools.merge(str(tmp_path / "a.mkv"), str(tmp_path / "b.mkv"),
                       cancel_event=event).status == S.CANCELLED
    assert tools.identify(str(tmp_path / "a.mkv"), cancel_event=event).cancelled
    assert fake_popen.instances == []


def test_finished_merge_with_exit_code_1_is_still_a_warning(tmp_path, fake_popen):
    fake_popen.hold_merge = False
    tools = MKVToolsWrapper("")
    original_exit = FakePopen._exit
    FakePopen._exit = lambda self, code: original_exit(self, 1 if code == 0 and not self.is_identify else code)
    try:
        result = tools.merge(str(tmp_path / "a.mkv"), str(tmp_path / "b.mkv"))
    finally:
        FakePopen._exit = original_exit
    assert result.status == S.COMPLETED_WITH_WARNINGS


def season(folder: Path, count: int = 1) -> list:
    for n in range(1, count + 1):
        (folder / f"Show - {n:02d}.mkv").write_bytes(b"video")
        write_srt(folder / f"Show - {n:02d}.srt")
    videos, subs = scan_folder(folder)
    return match_files(videos, subs)[0]


def test_killed_merge_leaves_no_output_and_no_partial(tmp_path, fake_popen):
    matches = season(tmp_path)
    tools = MKVToolsWrapper("")
    processor = EpisodeProcessor(tools, ProcessingOptions())
    holder = {}
    progress = threading.Event()
    thread = threading.Thread(target=lambda: holder.setdefault(
        "result", processor.process(matches[0], progress_callback=lambda pct: progress.set())))
    thread.start()
    assert progress.wait(10)
    out_dir = tmp_path / "PROCESSED"
    assert (out_dir / "Show - 01.mkv.partial").exists()
    tools.terminate_all()
    thread.join(10)
    assert holder["result"].status == S.CANCELLED
    assert list(out_dir.iterdir()) == []


def test_force_cancel_during_identify_starts_no_merge(tmp_path, fake_popen):
    """R2-02: identify is registered too, and nothing starts once the batch is stopped."""
    fake_popen.hold_identify = True
    matches = season(tmp_path, 3)
    tools = MKVToolsWrapper("")
    options = ProcessingOptions()
    batch = BatchProcessor(EpisodeProcessor(tools, options), max_workers=1)
    holder = {}
    thread = threading.Thread(target=lambda: holder.setdefault(
        "result", batch.process_all(matches, options)))
    thread.start()
    assert fake_popen.started_any.wait(10)
    assert fake_popen.instances[0].is_identify           # episode 1 is inside identify
    batch.cancel(force=True)
    thread.join(10)
    assert not thread.is_alive()
    result = holder["result"]
    assert result.cancelled == 3 and result.successful == 0
    assert merges(fake_popen) == []                      # no mkvmerge was started afterwards
    assert len(fake_popen.instances) == 1
    assert not (tmp_path / "PROCESSED").exists() or not list((tmp_path / "PROCESSED").iterdir())
