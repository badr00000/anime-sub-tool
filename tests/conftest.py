"""Shared fixtures.

Every test runs with the user's home redirected to a temp folder, so the real
config and logs in %USERPROFILE%\\.anime-sub-tool are never read or written.
"""

import os
import sys
import wave
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MKVMERGE = ROOT / "bin" / "mkvmerge.exe"

SRT_TEXT = (
    "1\r\n00:00:01,000 --> 00:00:02,000\r\nHello\r\n\r\n"
    "2\r\n00:00:03,000 --> 00:00:04,500\r\nWorld\r\n"
)


def pytest_configure(config):
    config.addinivalue_line("markers", "mkvmerge: needs the real bin/mkvmerge.exe")


def pytest_collection_modifyitems(config, items):
    if MKVMERGE.is_file():
        return
    skip = pytest.mark.skip(reason="bin/mkvmerge.exe is missing")
    for item in items:
        if "mkvmerge" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path_factory, monkeypatch):
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    assert Path.home() == home
    return home


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def write_srt(path: Path, text: str = SRT_TEXT, encoding: str = "utf-8") -> Path:
    path.write_bytes(text.encode(encoding))
    return path


def make_wav(path: Path, seconds: float = 0.5) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * seconds))
    return path
