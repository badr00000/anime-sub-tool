"""
Anime Subtitle Automation Tool v2.0 — Main Application Window

PySide6 QMainWindow with step-based navigation (Input → Preview → Processing → Results).
Background work runs in QThread with Signal/Slot communication.
"""

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QVBoxLayout, QWidget,
    QHBoxLayout, QPushButton, QStatusBar, QCheckBox,
)
from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QFont, QIcon

from core.config import load_config
from core.constants import (
    APP_NAME, APP_VERSION, DEFAULT_WINDOW_HEIGHT, DEFAULT_WINDOW_WIDTH,
    MIN_WINDOW_HEIGHT, MIN_WINDOW_WIDTH,
)
from core.engine import ProcessingEngine
from core.mkvtools import MKVToolsWrapper
from core.models import AppConfig
from gui.dialogs import messages
from gui.dialogs.about_dialog import AboutDialog
from gui.dialogs.settings_dialog import SettingsDialog
from gui.theme import Colors, add_glow, apply_palette, get_stylesheet, page_header
from gui.widgets.folder_picker import FolderPicker
from gui.widgets.log_panel import LogPanel
from gui.widgets.options_panel import OptionsPanel
from gui.widgets.preview_panel import PreviewPanel
from gui.widgets.progress_panel import ProgressPanel
from gui.widgets.results_panel import ResultsPanel
from gui.widgets.sidebar import Sidebar
from gui.widgets.sync_page import SyncPage
from utils.logger import get_logger, setup_logging
from utils.paths import resource_path

logger = get_logger(__name__)

# How long closing the window waits for background work to stop
_QUIT_WAIT_MS = 15000


class ScanWorker(QThread):
    """Background thread for folder scanning."""
    completed = Signal(object)
    error = Signal(str)

    def __init__(self, folder_path: str, config: AppConfig, auto: bool = False):
        super().__init__()
        self.folder_path = folder_path
        self.config = config
        # True when the watcher started this scan: no dialogs, the user did not ask for it
        self.auto = auto

    def run(self):
        try:
            engine = ProcessingEngine(self.config)
            self.completed.emit(engine.scan_and_match(self.folder_path))
        except Exception as e:
            logger.exception("Scan failed")
            self.error.emit(str(e))


class ProcessWorker(QThread):
    """Background thread for batch processing."""
    progress_updated = Signal(int, int, str)  # current, total, filename
    log_message = Signal(str, str)             # message, level
    completed = Signal(object)                 # BatchResult
    error = Signal(str)

    def __init__(self, scan_result, options, config: AppConfig):
        super().__init__()
        self.scan_result = scan_result
        self.options = options
        # Created here, not in run(), so cancel() works from the first moment
        self._engine = ProcessingEngine(config)

    def cancel(self, force: bool = False):
        self._engine.cancel(force=force)

    def run(self):
        try:
            def progress_cb(episode_num, file_progress, overall_progress):
                self.progress_updated.emit(overall_progress, 100, f"Episode {episode_num}")

            def log_cb(msg, level="INFO"):
                self.log_message.emit(msg, level)

            result = self._engine.process_batch(
                self.scan_result, self.options, progress_cb, log_cb
            )
            self.completed.emit(result)
        except Exception as e:
            logger.exception("Batch failed")
            self.error.emit(str(e))


class AnimeSubToolApp(QMainWindow):
    """Main application window with step-based wizard navigation."""

    def __init__(self, config: AppConfig | None = None):
        super().__init__()

        # The one configuration object: Settings and the options panel (presets)
        # both edit and save this same instance.
        self.config = config if config is not None else load_config()

        # Window setup
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)

        # Apply theme to the whole application (dialogs and message boxes included)
        apply_palette(QApplication.instance())
        QApplication.instance().setStyleSheet(get_stylesheet())

        # Set font
        font = QFont("Segoe UI", 10)
        font.setStyleHint(QFont.StyleHint.SansSerif)
        self.setFont(font)

        # State
        self.scan_result = None
        self._scan_worker = None
        self._rescan_pending = False
        self._process_worker = None
        self._last_options = None
        self.watcher = None

        # Build UI
        self._setup_ui()
        self._setup_statusbar()

    def _setup_statusbar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready — Select a folder to begin")

    _page_header = staticmethod(page_header)

    def _setup_ui(self):
        from gui.widgets.animated_background import AnimatedBackground
        central = AnimatedBackground()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar(APP_VERSION)
        self.sidebar.settings_requested.connect(self._show_settings)
        self.sidebar.about_requested.connect(self._show_about)
        self.sidebar.mode_requested.connect(self._switch_mode)
        self._merge_step = 0
        root.addWidget(self.sidebar)

        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(36, 30, 36, 24)
        main_layout.setSpacing(0)
        root.addWidget(content, 1)

        self.stack = QStackedWidget()

        # ─── Step 1: Input ───
        step1 = QWidget()
        s1_layout = QVBoxLayout(step1)
        s1_layout.setContentsMargins(0, 0, 0, 0)
        s1_layout.setSpacing(16)

        self.folder_picker = FolderPicker()
        self.folder_picker.path_changed.connect(self._on_path_changed)

        self.watch_cb = QCheckBox("Watch folder — rescan automatically when new files arrive")
        self.watch_cb.toggled.connect(self._toggle_watcher)

        self.scan_btn = QPushButton("SCAN FOLDER  ▸")
        self.scan_btn.setObjectName("primaryButton")
        self.scan_btn.setFixedSize(230, 48)
        self.scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scan_btn.clicked.connect(lambda: self._run_scan())
        add_glow(self.scan_btn, Colors.blue, 28)

        actions = QHBoxLayout()
        actions.addWidget(self.watch_cb)
        actions.addStretch()
        actions.addWidget(self.scan_btn)

        s1_layout.addWidget(self._page_header(
            "SELECT SOURCE", "Pick the folder that holds the season's episodes and its subtitle files."))
        s1_layout.addSpacing(8)
        s1_layout.addWidget(self.folder_picker)
        s1_layout.addStretch(1)
        s1_layout.addLayout(actions)

        # ─── Step 2: Preview ───
        step2 = QWidget()
        s2_layout = QVBoxLayout(step2)
        s2_layout.setContentsMargins(0, 0, 0, 0)
        s2_layout.setSpacing(14)

        self.preview_panel = PreviewPanel()
        self.options_panel = OptionsPanel(self.config)
        self.options_panel.setFixedWidth(340)

        split = QHBoxLayout()
        split.setSpacing(18)
        split.addWidget(self.preview_panel, 1)
        split.addWidget(self.options_panel)

        nav2 = QHBoxLayout()
        back2_btn = QPushButton("◂  BACK")
        back2_btn.setFixedHeight(44)
        back2_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back2_btn.clicked.connect(lambda: self._go_to_step(0))
        self.process_btn = QPushButton("START PROCESSING  ▸")
        self.process_btn.setObjectName("primaryButton")
        self.process_btn.setFixedSize(250, 48)
        self.process_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.process_btn.clicked.connect(self._start_processing)
        add_glow(self.process_btn, Colors.blue, 28)
        nav2.addWidget(back2_btn)
        nav2.addStretch()
        nav2.addWidget(self.process_btn)

        s2_layout.addWidget(self._page_header(
            "PREVIEW", "Check every episode got the right subtitle, then tune the options on the right."))
        s2_layout.addLayout(split, 1)
        s2_layout.addLayout(nav2)

        # ─── Step 3: Processing ───
        step3 = QWidget()
        s3_layout = QVBoxLayout(step3)
        s3_layout.setContentsMargins(0, 0, 0, 0)
        s3_layout.setSpacing(16)

        self.progress_panel = ProgressPanel()
        self.progress_panel.cancel_requested.connect(self._cancel_processing)
        self.log_panel = LogPanel()

        s3_layout.addWidget(self._page_header(
            "PROCESSING", "Merging subtitles and cleaning tracks. The original files are never modified."))
        s3_layout.addWidget(self.progress_panel)
        s3_layout.addWidget(self.log_panel, 1)

        # ─── Step 4: Results ───
        step4 = QWidget()
        s4_layout = QVBoxLayout(step4)
        s4_layout.setContentsMargins(0, 0, 0, 0)

        self.results_panel = ResultsPanel()
        self.results_panel.process_another_requested.connect(lambda: self._go_to_step(0))
        self.results_panel.open_folder_requested.connect(self._open_output_folder)
        s4_layout.addWidget(self.results_panel)

        for page in (step1, step2, step3, step4):
            self.stack.addWidget(page)

        # ─── Standalone tool: Sync Subtitle (index 4, not part of the merge steps) ───
        self.sync_page = SyncPage()
        self.sync_page.status_message.connect(self.status_bar_message)
        self.stack.addWidget(self.sync_page)

        main_layout.addWidget(self.stack, 1)

    SYNC_PAGE = 4

    def status_bar_message(self, text: str):
        if hasattr(self, "status_bar"):
            self.status_bar.showMessage(text, 8000)

    def _in_sync_mode(self) -> bool:
        return self.stack.currentIndex() == self.SYNC_PAGE

    def _switch_mode(self, mode: str):
        if mode == "sync":
            self.stack.setCurrentIndex(self.SYNC_PAGE)
        else:
            self.sync_page.pause()
            self.stack.setCurrentIndex(self._merge_step)
        self.sidebar.set_mode(mode)

    def _go_to_step(self, step: int):
        # Merge steps keep advancing in the background while the sync tool is open
        # (e.g. a batch finishes); only switch the view when the merge tool is showing.
        self._merge_step = step
        self.sidebar.set_step(step)
        if not self._in_sync_mode():
            self.stack.setCurrentIndex(step)

    # ─── Startup / shutdown ───

    def check_tools(self) -> bool:
        """Verify once at start that mkvmerge can run; tell the user clearly when not."""
        ok, message = MKVToolsWrapper(self.config.mkvtoolnix_path).validate_installation()
        if ok:
            logger.info(f"Using {message}")
            return True
        logger.error(message)
        self.status_bar.showMessage("mkvmerge is not available — merging will fail")
        messages.error(
            self, "MKVToolNix not available",
            f"{message}\n\nMerging needs mkvmerge. Sync Subtitle still works.\n"
            "Fix: open Settings and clear the MKVToolNix folder to use the bundled copy, "
            "or point it to a folder that contains mkvmerge.")
        return False

    def _batch_running(self) -> bool:
        return self._process_worker is not None and self._process_worker.isRunning()

    def _confirm_quit(self) -> bool:
        return messages.confirm(
            self, "Batch still running",
            "Episodes are still being processed.\n\nStop the batch and quit? "
            "Episodes that are not finished will be cancelled; finished ones are kept.")

    def closeEvent(self, event):
        if self._batch_running():
            if not self._confirm_quit():
                event.ignore()
                return
            self._process_worker.cancel(force=True)
            self._process_worker.wait(_QUIT_WAIT_MS)
        if self._scan_worker is not None:
            self._scan_worker.wait(_QUIT_WAIT_MS)
        if self.watcher is not None:
            self.watcher.stop()
            self.watcher = None
        self.sync_page.shutdown()
        super().closeEvent(event)

    def _cancel_processing(self):
        if self._batch_running():
            self._process_worker.cancel()
            self.progress_panel.cancel_btn.setEnabled(False)
            self.progress_panel.cancel_btn.setText("CANCELLING…")
            self.log_panel.append_log(
                "Cancel requested: episodes already running will finish, the rest are skipped.", "WARNING")

    # ─── Step 1: Scan ───

    def _on_path_changed(self, new_path: str):
        if self.watch_cb.isChecked():
            self.watch_cb.setChecked(False)

    def _toggle_watcher(self, checked: bool):
        from core.watcher import FolderWatcher

        if checked:
            path = self.folder_picker.get_path()
            if not path or not Path(path).is_dir():
                messages.warn(self, "Warning", "Please select a folder to watch first.")
                self.watch_cb.setChecked(False)
                return

            if self.watcher is not None:
                self.watcher.stop()

            self.watcher = FolderWatcher(path)
            self.watcher.folder_changed.connect(self._on_folder_changed)
            self.watcher.start()
            self.status_bar.showMessage(f"Watching folder for changes: {path}")
        else:
            if self.watcher is not None:
                self.watcher.stop()
                self.watcher = None
                self.status_bar.showMessage("Stopped watching folder.")

    def _on_folder_changed(self):
        self._run_scan(auto=True)

    def _run_scan(self, auto: bool = False):
        # Prevent watch folder from interrupting an active processing session
        if self._merge_step >= 2:
            return

        # One scan at a time: replacing a QThread that is still running destroys it
        # mid-run and takes the whole process down. Remember the request instead.
        if self._scan_worker is not None:
            self._rescan_pending = True
            return

        path = self.folder_picker.get_path()
        if not path or not Path(path).is_dir():
            if not auto:
                messages.warn(self, "Warning", "Please select an existing folder first.")
            return

        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("SCANNING…")
        self.status_bar.showMessage("Scanning folder...")

        worker = ScanWorker(path, self.config, auto=auto)
        worker.completed.connect(self._on_scan_completed)
        worker.error.connect(self._on_scan_error)
        worker.finished.connect(self._on_scan_finished)
        # The reference is kept until `finished`: see _on_scan_finished
        self._scan_worker = worker
        worker.start()

    def _on_scan_finished(self):
        worker, self._scan_worker = self._scan_worker, None
        if worker is not None:
            worker.deleteLater()
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("SCAN FOLDER  ▸")
        if self._rescan_pending:
            self._rescan_pending = False
            self._run_scan(auto=True)

    def _on_scan_completed(self, result):
        if self._merge_step >= 2:
            return  # a batch started meanwhile; keep the scan it is working on
        auto = bool(getattr(self.sender(), "auto", False))
        self.scan_result = result

        episode_count = len(result.matches)
        matched = sum(1 for m in result.matches if m.is_matched)
        self.status_bar.showMessage(
            f"Scan complete — {episode_count} episode(s), {matched} with a subtitle")

        if episode_count == 0:
            if not auto:
                messages.info(
                    self, "No Videos Found",
                    "No video files were found in the selected folder. Check that your folder "
                    "contains episode files (.mkv, .mp4, ...).")
            return

        self.preview_panel.populate(result)
        self._go_to_step(1)

    def _on_scan_error(self, err):
        self.status_bar.showMessage("Scan failed")
        if not getattr(self.sender(), "auto", False):
            messages.error(self, "Scan Error", f"Failed to scan folder:\n\n{err}")

    # ─── Step 2: Process ───

    def _start_processing(self):
        if not self.scan_result or self._batch_running():
            return

        options = self.options_panel.get_options()
        self._last_options = options

        self._go_to_step(2)
        self.progress_panel.reset()
        self.progress_panel.cancel_btn.setEnabled(True)
        self.progress_panel.cancel_btn.setText("CANCEL")
        self.log_panel.clear()
        self.status_bar.showMessage("Dry run..." if options.dry_run else "Processing...")

        worker = ProcessWorker(self.scan_result, options, self.config)
        worker.progress_updated.connect(self.progress_panel.update_progress)
        worker.log_message.connect(self.log_panel.append_log)
        worker.completed.connect(self._on_processing_completed)
        worker.error.connect(self._on_processing_error)
        worker.finished.connect(self._on_process_finished)
        self._process_worker = worker
        worker.start()

    def _on_process_finished(self):
        worker, self._process_worker = self._process_worker, None
        if worker is not None:
            worker.deleteLater()

    def _on_processing_completed(self, result):
        self.results_panel.show_results(result)
        self.status_bar.showMessage(self.results_panel.title.text().title())
        self._go_to_step(3)

    def _on_processing_error(self, err):
        self.status_bar.showMessage("Processing failed")
        messages.error(self, "Processing Error", f"Processing failed:\n\n{err}")
        self._go_to_step(1)

    # ─── Dialogs ───

    def _show_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec():
            # New defaults apply right away to the options panel
            self.options_panel.apply_config_defaults()

    def _show_about(self):
        dlg = AboutDialog(self)
        dlg.exec()

    def output_folder(self) -> Path | None:
        """The folder the last batch wrote to (the source folder if it was never created)."""
        if not self.scan_result or not self.scan_result.folder_path:
            return None
        source = Path(self.scan_result.folder_path)
        options = self._last_options or self.options_panel.get_options()
        output = ProcessingEngine.output_dir(self.scan_result, options)
        return output if output.is_dir() else source

    def _open_output_folder(self):
        folder = self.output_folder()
        if folder is None:
            return
        try:
            if sys.platform == 'win32':
                os.startfile(str(folder))
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', str(folder)])
            else:
                subprocess.Popen(['xdg-open', str(folder)])
        except Exception as e:
            messages.warn(self, "Error", f"Could not open folder:\n{e}")


def main():
    """Launch the GUI application."""
    setup_logging()

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")  # Cross-platform consistent style

    # Ensure Windows uses our custom icon in the taskbar
    if sys.platform == 'win32':
        import ctypes
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                f"AnimeSubTool.AnimeSubtitleAutomationTool.{APP_VERSION}")
        except (AttributeError, OSError):
            pass

    app.setWindowIcon(QIcon(str(resource_path('app_icon.ico'))))

    window = AnimeSubToolApp()
    window.show()
    QTimer.singleShot(0, window.check_tools)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
