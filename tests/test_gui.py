"""Offscreen GUI smoke tests (QT_QPA_PLATFORM=offscreen is set in conftest)."""

import time
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QLabel

from conftest import SRT_TEXT, write_srt
from core.config import load_config, save_config
from core.models import (
    AppConfig, BatchResult, ProcessingOptions, ProcessingResult, ProcessingStatus as S,
)


def pump(condition, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QApplication.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def dialogs(monkeypatch):
    """Record message boxes instead of showing them (they would block the test)."""
    from gui.dialogs import messages
    shown = []
    answers = {"confirm": True}
    for kind in ("info", "warn", "error"):
        monkeypatch.setattr(messages, kind,
                            lambda parent, title, text, kind=kind: shown.append((kind, title, text)))
    monkeypatch.setattr(messages, "confirm",
                        lambda parent, title, text: shown.append(("confirm", title, text)) or answers["confirm"])
    shown_answers = type("Dialogs", (), {"shown": shown, "answers": answers})
    return shown_answers


@pytest.fixture
def window(qapp, dialogs):
    from gui.app import AnimeSubToolApp
    w = AnimeSubToolApp()
    yield w
    # A real worker still running is stopped and waited for: dropping the reference
    # would hide it and let the QThread be destroyed while it runs. Stand-ins that
    # tests put in place are simply removed.
    from PySide6.QtCore import QThread
    for name in ("_process_worker", "_scan_worker"):
        worker = getattr(w, name, None)
        if isinstance(worker, QThread):
            if worker.isRunning():
                if hasattr(worker, "cancel"):
                    worker.cancel(force=True)
                assert worker.wait(30_000), f"{name} did not stop"
        elif worker is not None:
            setattr(w, name, None)
    w.close()
    QApplication.processEvents()


@pytest.fixture
def season(tmp_path):
    for n in (1, 2):
        (tmp_path / f"Show - {n:02d}.mkv").write_bytes(b"video")
        write_srt(tmp_path / f"Show - {n:02d}.srt")
    return tmp_path


# ── H1 / startup ──

def test_window_constructs_and_shares_one_config(window):
    assert window.options_panel.config is window.config
    assert not hasattr(window, "series_input")
    assert window.stack.count() == 5


def test_main_starts_without_name_error(qapp, dialogs, monkeypatch):
    import gui.app as app_module
    assert app_module.Path is Path                       # imported at module level
    created = []
    original_init = app_module.AnimeSubToolApp.__init__

    def tracking_init(self, *a, **kw):
        original_init(self, *a, **kw)
        created.append(self)

    monkeypatch.setattr(app_module.AnimeSubToolApp, "__init__", tracking_init)
    monkeypatch.setattr(app_module, "setup_logging", lambda **kw: None)
    monkeypatch.setattr(QApplication, "exec", lambda *a: 0)
    with pytest.raises(SystemExit) as exit_info:
        app_module.main()
    assert exit_info.value.code == 0
    assert len(created) == 1 and created[0].isVisible()
    created[0].close()


def test_check_tools_reports_a_missing_mkvmerge(window, dialogs, monkeypatch):
    assert window.check_tools() is True
    assert dialogs.shown == []
    from core.mkvtools import MKVToolsWrapper
    monkeypatch.setattr(MKVToolsWrapper, "validate_installation",
                        lambda self: (False, r"mkvmerge could not be started (X:\bin\mkvmerge.exe): gone"))
    assert window.check_tools() is False
    kind, title, text = dialogs.shown[-1]
    assert kind == "error" and r"X:\bin\mkvmerge.exe" in text and "mkvmerge" in text


# ── M2: scans ──

def test_double_scan_does_not_crash_and_reruns_once(window, season, monkeypatch):
    import threading
    from core.engine import ProcessingEngine
    calls = []
    entered = threading.Event()
    gate = threading.Event()             # the first scan stays inside until released
    original = ProcessingEngine.scan_and_match

    def gated_scan(self, folder):
        calls.append(folder)
        entered.set()
        assert gate.wait(10)
        return original(self, folder)

    monkeypatch.setattr(ProcessingEngine, "scan_and_match", gated_scan)
    window.folder_picker.set_path(str(season))
    window._run_scan()
    first_worker = window._scan_worker
    assert entered.wait(10)                  # the first scan is certainly running
    window._run_scan()                       # while the first is running
    window._on_folder_changed()              # and the watcher fires too
    assert window._scan_worker is first_worker and window._rescan_pending is True
    assert not window.scan_btn.isEnabled() and len(calls) == 1
    gate.set()

    assert pump(lambda: len(calls) == 2 and window._scan_worker is None)
    assert window._rescan_pending is False
    assert window.scan_btn.isEnabled()
    assert window._merge_step == 1 and len(window.scan_result.matches) == 2
    assert window.scan_result.folder_path == season.resolve()


def test_scan_without_folder_warns_but_watcher_scan_is_silent(window, dialogs):
    window._run_scan()
    assert dialogs.shown[-1][0] == "warn" and window._scan_worker is None
    dialogs.shown.clear()
    window._run_scan(auto=True)
    assert dialogs.shown == []


# ── preview ──

def test_preview_flags_uncertain_rows_and_shows_encoding(window, tmp_path):
    from core.engine import ProcessingEngine
    (tmp_path / "[Cleo]Mousou_Dairinin_-_01.mkv").write_bytes(b"v")
    write_srt(tmp_path / "[Scarlet] Paranoia Agent - 01.srt",
              SRT_TEXT.replace("Hello", "مرحبا بكم في هذا العالم الجميل"), "cp1256")
    (tmp_path / "Same - 02.mkv").write_bytes(b"v")
    write_srt(tmp_path / "Same - 02.srt")
    (tmp_path / "Lonely - 03.mkv").write_bytes(b"v")
    scan = ProcessingEngine(AppConfig()).scan_and_match(tmp_path)
    panel = window.preview_panel
    panel.populate(scan)
    rows = {panel.table.item(r, 1).text(): r for r in range(panel.table.rowCount())}

    low = rows["[Cleo]Mousou_Dairinin_-_01.mkv"]
    assert "CHECK" in panel.table.item(low, 4).text()
    assert "Paranoia Agent" in panel.table.item(low, 2).text()
    assert "Windows-1256 (Arabic)" in panel.table.item(low, 2).toolTip()
    assert panel.table.item(rows["Same - 02.mkv"], 4).text() == "READY"
    assert panel.table.item(rows["Lonely - 03.mkv"], 4).text() == "NO SUB"
    summary = panel.summary_label.text()
    assert "1 TO CHECK" in summary and "1 WITHOUT SUBTITLE" in summary


def test_tooltips_never_render_markup():
    from gui.theme import plain_tooltip
    tip = plain_tooltip('<img src="file:///C:/x.png"> & more\nline2')
    assert "<img" not in tip and "&lt;img" in tip and "<br>" in tip


# ── options / presets / settings (M4, M11, L9) ──

def test_options_panel_defaults_come_from_config(qapp):
    from gui.widgets.options_panel import OptionsPanel
    config = AppConfig(default_workers=6, output_subfolder="DONE", subtitle_language="eng",
                       subtitle_name="English subs")
    panel = OptionsPanel(config)
    options = panel.get_options()
    assert options.parallel_workers == 6 and options.output_folder == "DONE"
    assert (options.subtitle_language, options.subtitle_name) == ("eng", "English subs")
    assert options.overwrite_existing is False and options.process_unmatched is False
    assert "DONE/" in panel.subfolder_cb.text()
    panel.overwrite_cb.setChecked(True)
    panel.unmatched_cb.setChecked(True)
    options = panel.get_options()
    assert options.overwrite_existing and options.process_unmatched
    from core.subtitles import CHARSET_CHOICES
    labels = [panel.charset_combo.itemData(i) for i in range(panel.charset_combo.count())]
    assert labels == [value for _, value in CHARSET_CHOICES]
    for added in ("cp1251", "koi8_r", "cp1253", "cp1255", "cp874", "cp1250", "cp1254"):
        assert added in labels


def test_settings_and_presets_do_not_overwrite_each_other(window, dialogs):
    from gui.dialogs.settings_dialog import SettingsDialog
    panel = window.options_panel

    panel.overwrite_cb.setChecked(True)
    panel.worker_spin.setValue(2)
    panel.save_preset("mine")
    assert load_config().presets["mine"]["overwrite_existing"] is True

    dlg = SettingsDialog(window.config, window)
    dlg.workers_spin.setValue(7)
    dlg.subfolder_edit.setText("DONE")
    dlg.sub_lang_edit.set_value("eng")
    dlg.mkv_path_edit.setText("")
    dlg._save()
    window.options_panel.apply_config_defaults()
    on_disk = load_config()
    assert on_disk.default_workers == 7 and on_disk.output_subfolder == "DONE"
    assert on_disk.subtitle_language == "eng" and on_disk.subtitle_name == "English"
    assert on_disk.mkvtoolnix_path == ""
    assert "mine" in on_disk.presets                       # Settings did not wipe the preset
    assert panel.get_options().output_folder == "DONE"
    assert panel.worker_spin.value() == 7 and "DONE/" in panel.subfolder_cb.text()

    panel.save_preset("second")
    on_disk = load_config()
    assert set(on_disk.presets) == {"mine", "second"}
    assert on_disk.default_workers == 7 and on_disk.subtitle_language == "eng"   # preset did not revert Settings

    panel.preset_combo.setCurrentText("mine")
    assert panel.overwrite_cb.isChecked() and panel.worker_spin.value() == 2
    panel.preset_combo.setCurrentText("Default")
    assert not panel.overwrite_cb.isChecked() and panel.worker_spin.value() == 7


def test_settings_rejects_bad_values(window, dialogs, tmp_path):
    from gui.dialogs.settings_dialog import SettingsDialog
    dlg = SettingsDialog(window.config, window)
    dlg.subfolder_edit.setText("..\\outside")
    dlg._save()
    assert dialogs.shown[-1][0] == "warn" and window.config.output_subfolder == "PROCESSED"
    dlg.subfolder_edit.setText("PROCESSED")
    dlg.mkv_path_edit.setText(str(tmp_path))               # no mkvmerge in there
    dlg._save()
    assert dialogs.shown[-1][1] == "MKVToolNix" and window.config.mkvtoolnix_path == ""
    assert dlg.result() == 0


def test_bad_preset_values_are_ignored(qapp):
    from gui.widgets.options_panel import OptionsPanel
    config = AppConfig(presets={"broken": {
        "workers": "x", "keep_audio_langs": "jpn", "keep_sub_langs": 5, "dry_run": "yes",
        "subtitle_offset_ms": "soon", "subtitle_charset": 12, "subtitle_language": None,
        "remove_existing_subs": "no", "backup_originals": True,
    }, "notadict": "abc"})
    panel = OptionsPanel(config)
    panel.preset_combo.setCurrentText("broken")
    options = panel.get_options()
    assert options.keep_audio_langs == ["jpn"]             # not ['j', 'p', 'n']
    assert options.parallel_workers == 4 and options.keep_sub_langs == []
    assert options.dry_run is False and options.subtitle_offset_ms == 0
    assert options.subtitle_charset == "auto" and options.subtitle_language == "ara"
    assert options.remove_existing_subs is True
    panel.preset_combo.setCurrentText("notadict")
    assert panel.get_options().keep_audio_langs == ["jpn"]


# ── results (L1, L2, M6, L5) ──

def result_of(*statuses, dry_run=False):
    results = [ProcessingResult(status=s, message=f"msg {i} <b>x</b>") for i, s in enumerate(statuses)]
    count = lambda *wanted: sum(1 for s in statuses if s in wanted)
    return BatchResult(total=len(statuses), successful=count(S.COMPLETED, S.COMPLETED_WITH_WARNINGS),
                       failed=count(S.FAILED), cancelled=count(S.CANCELLED), skipped=count(S.SKIPPED),
                       dry_run=dry_run, results=results)


@pytest.mark.parametrize("statuses, dry_run, state, title", [
    ((S.COMPLETED, S.COMPLETED), False, "complete", "MISSION COMPLETE"),
    ((S.COMPLETED, S.SKIPPED), False, "complete", "MISSION COMPLETE"),
    ((S.COMPLETED, S.FAILED), False, "errors", "COMPLETED WITH ERRORS"),
    ((S.COMPLETED, S.CANCELLED, S.CANCELLED), False, "cancelled", "CANCELLED"),
    ((S.COMPLETED, S.COMPLETED), True, "dry_run", "DRY RUN — NOTHING WRITTEN"),
    ((S.SKIPPED, S.SKIPPED), False, "nothing", "NOTHING PROCESSED"),
])
def test_results_states(qapp, statuses, dry_run, state, title):
    from gui.widgets.results_panel import ResultsPanel
    panel = ResultsPanel()
    panel.show_results(result_of(*statuses, dry_run=dry_run))
    assert panel.state == state and panel.title.text() == title
    if state != "complete":
        assert "ready in the output folder" not in panel.subtitle.text()
    assert panel.skipped_value.text() == str(statuses.count(S.SKIPPED))
    assert panel.cancelled_value.text() == str(statuses.count(S.CANCELLED))
    assert panel.failed_value.text() == str(statuses.count(S.FAILED))
    assert panel.title.textFormat() == Qt.TextFormat.PlainText
    assert panel.subtitle.textFormat() == Qt.TextFormat.PlainText
    if dry_run:
        assert "No file was created" in panel.subtitle.text()
        assert panel.success_label.text() == "WOULD DO"


def test_open_output_folder_targets_the_real_output(window, season, monkeypatch):
    import gui.app as app_module
    from core.engine import ProcessingEngine
    opened = []
    monkeypatch.setattr(app_module.os, "startfile", lambda p: opened.append(p), raising=False)
    window.scan_result = ProcessingEngine(window.config).scan_and_match(season)

    window._last_options = ProcessingOptions()
    assert window.output_folder() == season                   # PROCESSED/ not created (e.g. dry run)
    (season / "PROCESSED").mkdir()
    assert window.output_folder() == season / "PROCESSED"
    window._open_output_folder()
    assert opened == [str(season / "PROCESSED")]

    elsewhere = season / "custom"
    elsewhere.mkdir()
    window._last_options = ProcessingOptions(output_dir=elsewhere)
    assert window.output_folder() == elsewhere
    window._last_options = ProcessingOptions(create_output_folder=False)
    assert window.output_folder() == season


def test_full_dry_run_through_the_window(window, season):
    window.folder_picker.set_path(str(season))
    window._run_scan()
    assert pump(lambda: window._merge_step == 1 and window._scan_worker is None)
    window.options_panel.dry_run_cb.setChecked(True)
    window._start_processing()
    assert pump(lambda: window._merge_step == 3 and window._process_worker is None)
    assert window.results_panel.state == "dry_run"
    assert window.results_panel.success_value.text() == "2"
    assert not (season / "PROCESSED").exists()
    assert "[DRY RUN]" in window.log_panel.text_edit.toPlainText()


# ── L3: closing ──

class StubWorker:
    def __init__(self):
        self.cancelled = []
        self.waited = []

    def isRunning(self):
        return True

    def cancel(self, force=False):
        self.cancelled.append(force)

    def wait(self, ms):
        self.waited.append(ms)
        return True


def test_close_during_batch_asks_then_cancels_and_stops_everything(window, dialogs):
    stub = StubWorker()
    window._process_worker = stub
    stopped = []
    window.watcher = type("W", (), {"stop": lambda self: stopped.append("watcher")})()

    dialogs.answers["confirm"] = False
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted() and stub.cancelled == [] and stopped == []
    assert dialogs.shown[-1][0] == "confirm"

    dialogs.answers["confirm"] = True
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()
    assert stub.cancelled == [True] and len(stub.waited) == 1 and stub.waited[0] > 0
    assert stopped == ["watcher"] and window.watcher is None
    assert not window.sync_page._tick.isActive()


# ── language picker ──

def test_language_picker_search(qapp):
    from gui.widgets.language_picker import LanguageCombo, MultiLanguageCombo
    combo = LanguageCombo()
    popup = combo._popup

    def search(text):
        popup.search.clear()
        popup.search.insert(text)          # insert(): keyClicks crashes on non-ASCII here
        return [popup.proxy.index(r, 0).data() for r in range(popup.proxy.rowCount())]

    assert search("japan") == ["Japanese (jpn)"]
    assert search("fra") == ["French (fre)"]
    assert search("ياباني") == ["Japanese (jpn)"]
    assert search("يابانى") == ["Japanese (jpn)"]          # alef maqsura folded
    assert "Arabic (ara)" in search("عربي")
    assert search("zzzz") == [] and not popup.empty.isHidden()
    assert len(search("")) == combo.count()

    search("ياباني")
    popup._activate(popup.proxy.index(0, 0))
    assert combo.value() == "jpn"

    multi = MultiLanguageCombo()
    multi.set_values(["ja", "eng", "xyz"])
    assert multi.values() == ["jpn", "eng", "xyz"]


# ── sync page (M1, L6, L7, M9) ──

@pytest.fixture
def sync(qapp, dialogs):
    from gui.widgets.sync_page import SyncPage
    page = SyncPage()
    yield page
    page.shutdown()


def test_sync_labels_are_plain_text(sync, tmp_path):
    evil = ("1\n00:00:00,000 --> 00:00:09,000\n"
            "<<b>img src=\"file:///C:/Windows/win.ini\"<i>> &amp; <u>hi</u>\n")
    sync.load_subtitle(str(write_srt(tmp_path / "evil.srt", evil)))
    for label in (sync.line_lbl, sync.saved_lbl, sync.clamp_lbl):
        assert label.textFormat() == Qt.TextFormat.PlainText
    sync._refresh()
    assert "<" not in sync.line_lbl.text() and "img" not in sync.line_lbl.text()
    assert "<qt>" in sync.sub_field.edit.toolTip()


def test_sync_warns_when_lines_go_before_zero(sync, tmp_path):
    sync.load_subtitle(str(write_srt(tmp_path / "a.srt")))
    assert sync.clamp_lbl.isHidden()
    sync.set_offset(-2500)
    assert not sync.clamp_lbl.isHidden() and "1 line(s)" in sync.clamp_lbl.text()
    sync.set_offset(-9000)
    assert "2 line(s)" in sync.clamp_lbl.text()
    sync.set_offset(300)
    assert sync.clamp_lbl.isHidden()


def test_sync_save_never_silently_overwrites_the_source(sync, dialogs, tmp_path):
    src = write_srt(tmp_path / "Show - 01.srt")
    sync.load_subtitle(str(src))
    sync.set_offset(1000)
    sync.save()
    synced = tmp_path / "Show - 01.synced.srt"
    assert synced.exists() and src.read_bytes() == SRT_TEXT.encode()
    assert not [d for d in dialogs.shown if d[0] == "confirm"]

    # Save As onto the loaded file: asks first
    dialogs.answers["confirm"] = False
    sync._write(str(src))
    assert dialogs.shown[-1][0] == "confirm" and src.read_bytes() == SRT_TEXT.encode()

    # A file that is already '.synced': the default Save would overwrite its own source
    sync.load_subtitle(str(synced))
    before = synced.read_bytes()
    sync.set_offset(1000)
    sync.save()
    assert dialogs.shown[-1][0] == "confirm" and synced.read_bytes() == before
    dialogs.answers["confirm"] = True
    sync.save()
    assert synced.read_bytes() != before


def test_sync_loads_utf16_without_bom_and_rejects_empty(sync, dialogs, tmp_path):
    text = SRT_TEXT.replace("Hello", "مرحبا بكم في هذا العالم")
    sync.load_subtitle(str(write_srt(tmp_path / "u16.srt", text, "utf-16-le")))
    assert len(sync._cues) == 2 and sync._cues[0].text == "مرحبا بكم في هذا العالم"
    assert sync._sub.encoding == "utf-16-le"

    (tmp_path / "empty.srt").write_bytes(b"")
    sync.load_subtitle(str(tmp_path / "empty.srt"))
    assert dialogs.shown[-1][0] == "warn" and sync._sub.path.name == "u16.srt"


# ── misc ──

def test_folder_picker_counts_like_the_scanner(qapp, tmp_path):
    from gui.widgets.folder_picker import FolderPicker
    for name in ("a - 01.mkv", "a - 01 [AnimeSubTool].mkv", "a - 02.m2ts", "a - 01.idx",
                 "a - 01.sub", "a - 02.srt"):
        (tmp_path / name).write_bytes(b"x")
    picker = FolderPicker()
    picker.set_path(str(tmp_path))
    assert "2 EPISODE(S)" in picker.status_label.text() and "2 SUBTITLE(S)" in picker.status_label.text()


def test_about_dialog_shows_third_party_licenses(qapp):
    from gui.dialogs.about_dialog import AboutDialog, LicensesDialog, load_license_text
    about = AboutDialog()
    assert about.licenses_btn.text() == "Licenses"
    labels = " ".join(label.text() for label in about.findChildren(QLabel))
    assert "AI Development Team" not in labels and "MKVToolNix" in labels
    licenses = LicensesDialog()
    text = licenses.text.toPlainText()
    assert text == load_license_text()
    # The app's own MIT licence comes first, then the third-party notices
    assert text.startswith("MIT License")
    assert text.index("MIT License") < text.index("Third-party software")
    assert "Written offer" in text and "MKVToolNix 100.0" in text
    for needle in ("MKVToolNix", "codeberg.org/mbunkus/mkvtoolnix", "GNU GENERAL PUBLIC LICENSE",
                   "Version 2, June 1991", "PySide6", "Lesser General Public License", "anitopy",
                   "RapidFuzz", "click", "watchdog"):
        assert needle in text
    # No longer a dependency, so it must not be credited
    assert "charset-normalizer" not in text


def test_build_script_ships_licenses_and_only_mkvmerge():
    import importlib.util
    from conftest import ROOT
    spec = importlib.util.spec_from_file_location("build_script", ROOT / "build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)                     # PyInstaller is only imported by build()
    args = build.pyinstaller_args()
    data = {}
    for arg in args:
        if arg.startswith("--add-data="):
            source, target = arg[len("--add-data="):].rsplit(";", 1)
            data[Path(source)] = target
    assert data[ROOT / "LICENSE"] == "."
    assert data[ROOT / "THIRD_PARTY_LICENSES.md"] == "."
    assert data[ROOT / "licenses"] == "licenses"
    assert data[ROOT / "bin" / "mkvmerge.exe"] == "bin"
    assert ROOT / "bin" not in data                    # never the whole bin folder
    assert not any("mkvpropedit" in arg for arg in args)
    for source in data:
        assert source.exists(), source
    assert (ROOT / "licenses" / "GPL-2.0.txt").stat().st_size > 15000


# ── R2-02: closing waits until the batch has really stopped ───────────────────

class SlowStopWorker(StubWorker):
    """Keeps running until the force cancel has been sent a second time, like a
    batch where one mkvmerge was starting while the first terminate went out."""

    def __init__(self):
        super().__init__()
        self.finished = False

    def wait(self, ms):
        self.waited.append(ms)
        self.finished = len(self.cancelled) >= 2
        return self.finished


def test_close_keeps_stopping_until_the_worker_has_finished(window, dialogs, monkeypatch):
    import gui.app as app_module
    monkeypatch.setattr(app_module, "_QUIT_WAIT_STEP_MS", 1)
    worker = SlowStopWorker()
    window._process_worker = worker
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted() and worker.finished
    assert worker.cancelled == [True, True] and len(worker.waited) == 2


def test_close_with_a_real_engine_waits_for_the_thread(window, dialogs, season):
    """The QThread is finished when closeEvent returns: no 'destroyed while running'."""
    import threading
    from gui.app import ProcessWorker
    from core.models import FileInfo

    gate = threading.Event()

    class BlockingTools:
        def identify(self, path, cancel_event=None):
            gate.wait(10)
            return FileInfo(filepath=Path(path), error="Cancelled", cancelled=True)

        def terminate_all(self):
            gate.set()

    from core.engine import ProcessingEngine
    scan = ProcessingEngine(window.config).scan_and_match(season)
    worker = ProcessWorker(scan, ProcessingOptions(), window.config)
    worker._engine.mkv_tools = BlockingTools()
    worker.start()
    window._process_worker = worker
    window.closeEvent(QCloseEvent())
    assert worker.isFinished()
    window._process_worker = None


# ── R2-09: 'Default' preset name ──────────────────────────────────────────────

def test_preset_cannot_be_saved_as_default(window, dialogs, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    panel = window.options_panel
    count = panel.preset_combo.count()
    for name in ("Default", "default", " DEFAULT "):
        assert panel.save_preset(name) is False
    assert "Default" not in window.config.presets and panel.preset_combo.count() == count

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("default", True)))
    panel._save_preset()
    assert dialogs.shown[-1][0] == "warn" and "built-in" in dialogs.shown[-1][2]
    assert panel.preset_combo.count() == count


def test_preset_named_default_in_config_loads_and_deletes(qapp, dialogs):
    import json
    from core import config as cfg
    path = cfg._get_config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"presets": {"Default": {"workers": 2, "overwrite_existing": True}}}),
                    encoding="utf-8")
    from gui.widgets.options_panel import OptionsPanel
    panel = OptionsPanel(load_config())
    names = [panel.preset_combo.itemText(i) for i in range(panel.preset_combo.count())]
    assert names == ["Default", "Default (saved)"]          # no duplicate entry
    panel.preset_combo.setCurrentText("Default (saved)")
    assert panel.worker_spin.value() == 2 and panel.overwrite_cb.isChecked()
    panel._delete_preset()
    assert panel.preset_combo.findText("Default (saved)") == -1
    assert load_config().presets == {}


# ── R2-10: tooltips built from preset/config data are plain text ──────────────

def test_multi_language_tooltip_is_plain_text(qapp):
    from gui.widgets.language_picker import MultiLanguageCombo
    combo = MultiLanguageCombo()
    combo.set_values(["jpn", "<img src=x>"])
    tip = combo.toolTip()
    assert tip.startswith("<qt>") and "<img" not in tip and "&lt;img" in tip
    combo.set_values([])
    assert combo.toolTip() == ""


# ── R2-11: an invalid saved MKVToolNix folder does not block Settings ─────────

def test_settings_saves_other_fields_with_an_invalid_stored_folder(window, dialogs, tmp_path):
    from gui.dialogs.settings_dialog import SettingsDialog
    window.config.mkvtoolnix_path = str(tmp_path / "gone")
    dlg = SettingsDialog(window.config, window)
    assert not dlg.mkv_invalid.isHidden()                    # shown as invalid
    dlg.workers_spin.setValue(5)
    dlg._save()
    assert dlg.result() == dlg.DialogCode.Accepted and not dialogs.shown
    assert load_config().default_workers == 5

    dlg = SettingsDialog(window.config, window)
    dlg.mkv_path_edit.clear()                                # the offered fix
    assert dlg.mkv_invalid.isHidden()
    dlg._save()
    assert load_config().mkvtoolnix_path == ""

    dlg = SettingsDialog(window.config, window)              # a NEW bad folder is refused
    dlg.mkv_path_edit.setText(str(tmp_path / "typo"))
    dlg._save()
    assert dialogs.shown[-1][0] == "warn" and window.config.mkvtoolnix_path == ""


# ── R2-03: uncertain encoding is shown ────────────────────────────────────────

def test_preview_marks_uncertain_encoding(window, season):
    write_srt(season / "Show - 02.srt", SRT_TEXT.replace("Hello", "Да"), "cp1251")
    from core.engine import ProcessingEngine
    scan = ProcessingEngine(window.config).scan_and_match(season)
    window.preview_panel.populate(scan)
    table = window.preview_panel.table
    assert table.item(0, 4).text() == "READY"
    assert table.item(1, 4).text() == "⚠ ENCODING"
    assert table.item(1, 2).text().startswith("⚠ ")
    assert "encoding uncertain — choose it in Encoding" in table.item(1, 2).toolTip()
    assert "encoding uncertain — choose it in Encoding" in table.item(1, 4).toolTip()
    assert "ENCODING UNCERTAIN" in window.preview_panel.summary_label.text()


def test_sync_warns_on_uncertain_encoding_and_reloads_with_the_chosen_one(sync, dialogs, tmp_path):
    path = write_srt(tmp_path / "ru.srt", SRT_TEXT.replace("Hello", "Да"), "cp1251")
    sync.load_subtitle(str(path))
    assert not sync.encoding_warn.isHidden()
    assert sync.encoding_combo.currentData() == "auto"
    sync.set_offset(1500)

    sync._write(tmp_path / "out.srt")                        # refused while uncertain
    assert dialogs.shown[-1][0] == "warn" and not (tmp_path / "out.srt").exists()

    sync.encoding_combo.setCurrentIndex(sync.encoding_combo.findData("cp1251"))
    assert sync.encoding_warn.isHidden()
    assert sync._sub.encoding == "cp1251" and sync._cues[0].text == "Да"
    assert sync._offset == 1500                               # same file: offset kept
    sync._write(tmp_path / "out.srt")
    assert "Да" in (tmp_path / "out.srt").read_text(encoding="utf-8-sig")

    other = write_srt(tmp_path / "en.srt")
    sync.load_subtitle(str(other))
    assert sync.encoding_combo.currentData() == "auto" and sync.encoding_warn.isHidden()
