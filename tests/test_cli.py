import importlib
import subprocess
import sys

import pytest
from click.testing import CliRunner

from conftest import ROOT, SRT_TEXT, write_srt


@pytest.fixture
def cli(monkeypatch):
    import cli.commands as commands
    import utils.logger
    monkeypatch.setattr(commands, "setup_logging", lambda **kw: None)
    return commands.cli


def test_import_survives_missing_console_streams():
    """A windowed .exe has sys.stdout / sys.stderr set to None."""
    code = ("import sys; sys.stdout = None; sys.stderr = None; "
            "import cli.commands as c; "
            "c.safe_echo('still alive'); "
            "open(sys.argv[1], 'w').write('imported')")
    marker = ROOT / "tests" / ".cli_import_marker"
    try:
        run = subprocess.run([sys.executable, "-c", code, str(marker)], cwd=ROOT,
                             capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
        assert marker.read_text() == "imported"
    finally:
        marker.unlink(missing_ok=True)


def test_main_py_runs_cli_from_source():
    run = subprocess.run([sys.executable, str(ROOT / "main.py"), "version"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8")
    assert run.returncode == 0 and "Anime Subtitle Automation Tool v" in run.stdout


def test_dead_options_are_gone_and_new_ones_exist(cli):
    runner = CliRunner()
    help_text = runner.invoke(cli, ["process", "--help"]).output
    for flag in ("--overwrite", "--include-unmatched", "--output", "--workers", "--dry-run"):
        assert flag in help_text
    assert "--no-backup" not in help_text and "--name" not in help_text
    assert "--name" not in runner.invoke(cli, ["preview", "--help"]).output


@pytest.mark.parametrize("workers", ["0", "9", "-1", "abc"])
def test_workers_is_validated(cli, tmp_path, workers):
    result = CliRunner().invoke(cli, ["process", str(tmp_path), "--workers", workers, "-y"])
    assert result.exit_code == 2
    assert "--workers" in result.output


def test_scan_and_preview(cli, tmp_path):
    (tmp_path / "Show - 01.mkv").write_bytes(b"v")
    (tmp_path / "Show - NCOP1.mkv").write_bytes(b"v")
    write_srt(tmp_path / "Show - 01.srt")
    runner = CliRunner()
    scan = runner.invoke(cli, ["scan", str(tmp_path)])
    assert scan.exit_code == 0, scan.output
    assert "2 episode(s), 1 with a subtitle" in scan.output and "100% (EXACT)" in scan.output

    out_dir = tmp_path / "custom out"
    preview = runner.invoke(cli, ["preview", str(tmp_path), "--output", str(out_dir), "--offset", "-1.5"])
    assert preview.exit_code == 0, preview.output
    assert str(out_dir / "Show - 01.mkv") in preview.output
    assert "Shift Subtitle: 1.5s earlier" in preview.output
    assert "Skip: No matching subtitle" in preview.output
    assert not out_dir.exists()


def test_shift_writes_synced_copy_and_keeps_original(cli, tmp_path):
    src = write_srt(tmp_path / "Show - 01.srt")
    result = CliRunner().invoke(cli, ["shift", str(src), "--offset", "1.5"])
    assert result.exit_code == 0, result.output
    assert src.read_bytes() == SRT_TEXT.encode()
    synced = (tmp_path / "Show - 01.synced.srt").read_text(encoding="utf-8-sig")
    assert "00:00:02,500 --> 00:00:03,500" in synced
    assert "Warning" not in result.output


def test_shift_refuses_to_overwrite_its_source(cli, tmp_path):
    src = write_srt(tmp_path / "Show - 01.srt")
    runner = CliRunner()
    refused = runner.invoke(cli, ["shift", str(src), "--offset", "1", "-o", str(src)])
    assert refused.exit_code == 1 and "--force" in refused.output
    assert src.read_bytes() == SRT_TEXT.encode()

    synced = write_srt(tmp_path / "Other - 01.synced.srt")
    refused = runner.invoke(cli, ["shift", str(synced), "--offset", "1"])
    assert refused.exit_code == 1
    assert synced.read_bytes() == SRT_TEXT.encode()

    forced = runner.invoke(cli, ["shift", str(src), "--offset", "1", "-o", str(src), "--force"])
    assert forced.exit_code == 0, forced.output
    assert "00:00:02,000 --> 00:00:03,000" in src.read_text(encoding="utf-8-sig")


def test_shift_warns_about_lines_before_zero(cli, tmp_path):
    src = write_srt(tmp_path / "a.srt")
    result = CliRunner().invoke(cli, ["shift", str(src), "--offset", "-2.5"])
    assert result.exit_code == 0
    assert "Warning: 1 of 2 line(s) would start before 0:00" in result.output


def test_shift_on_empty_subtitle_fails(cli, tmp_path):
    empty = tmp_path / "empty.srt"
    empty.write_bytes(b"")
    result = CliRunner().invoke(cli, ["shift", str(empty), "--offset", "1"])
    assert result.exit_code == 1 and "no subtitle lines" in result.output
    assert not (tmp_path / "empty.synced.srt").exists()
