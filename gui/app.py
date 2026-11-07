"""
Anime Subtitle Automation Tool v2.0 — Main Application Window

PySide6 QMainWindow with step-based navigation (Input → Preview → Processing → Results).
Background work runs in QThread with Signal/Slot communication.
"""

import sys
import time
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QVBoxLayout, QWidget,
    QHBoxLayout, QPushButton, QMessageBox, QMenuBar, QMenu, QStatusBar,
    QCheckBox
)
from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QAction, QFont

from gui.theme import get_stylesheet
from gui.widgets.header import AppHeader
from gui.widgets.folder_picker import FolderPicker
from gui.widgets.series_input import SeriesInput
from gui.widgets.preview_panel import PreviewPanel
from gui.widgets.options_panel import OptionsPanel
from gui.widgets.progress_panel import ProgressPanel
from gui.widgets.log_panel import LogPanel
from gui.widgets.results_panel import ResultsPanel
from gui.dialogs.settings_dialog import SettingsDialog
from gui.dialogs.about_dialog import AboutDialog

try:
    from core.models import AppConfig, ProcessingOptions, ScanResult, BatchResult
    from core.config import load_config, save_config
    from core.engine import ProcessingEngine
    from core.constants import (
        MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT,
        DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT,
        APP_NAME, APP_VERSION
    )
    HAS_CORE = True
except ImportError:
    HAS_CORE = False
    AppConfig = None
    ProcessingOptions = None
    ScanResult = None
    BatchResult = None
    load_config = None
    save_config = None
    ProcessingEngine = None
    MIN_WINDOW_WIDTH = 900
    MIN_WINDOW_HEIGHT = 650
    DEFAULT_WINDOW_WIDTH = 1100
    DEFAULT_WINDOW_HEIGHT = 750
    APP_NAME = "Anime Subtitle Automation Tool"
    APP_VERSION = "2.0.0"


class ScanWorker(QThread):
    """Background thread for folder scanning."""
    completed = Signal(object)
    error = Signal(str)

    def __init__(self, folder_path: str, series_name: str):
        super().__init__()
        self.folder_path = folder_path
        self.series_name = series_name

    def run(self):
        try:
            if not ProcessingEngine:
                raise RuntimeError("Core engine not available. Check installation.")
            engine = ProcessingEngine()
            result = engine.scan_and_match(self.folder_path, self.series_name)
            self.completed.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class ProcessWorker(QThread):
    """Background thread for batch processing."""
    progress_updated = Signal(int, int, str)  # current, total, filename
    log_message = Signal(str, str)             # message, level
    completed = Signal(object)                 # BatchResult
    error = Signal(str)

    def __init__(self, scan_result, options):
        super().__init__()
        self.scan_result = scan_result
        self.options = options
        self._start_time = 0

    def run(self):
        try:
            if not ProcessingEngine:
                raise RuntimeError("Core engine not available.")

            engine = ProcessingEngine()
            self._start_time = time.time()
            self._processed = 0
            total = len(self.scan_result.matches)

            def progress_cb(episode_num, file_progress, overall_progress):
                """Called by batch processor with per-episode progress."""
                self.progress_updated.emit(overall_progress, 100, f"Episode {episode_num}")

            def log_cb(msg, level="INFO"):
                """Called by batch processor with log messages."""
                self.log_message.emit(msg, level)

            result = engine.process_batch(
                self.scan_result, self.options, progress_cb, log_cb
            )
            self.completed.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class AnimeSubToolApp(QMainWindow):
    """Main application window with step-based wizard navigation."""

    def __init__(self):
        super().__init__()

        # Load config
        self.config = load_config() if load_config else None

        # Window setup
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)

        # Apply theme
        self.setStyleSheet(get_stylesheet())

        # Set font
        font = QFont("Segoe UI", 10)
        font.setStyleHint(QFont.StyleHint.SansSerif)
        self.setFont(font)

        # State
        self.scan_result = None
        self._scan_worker = None
        self._process_worker = None

        # Build UI
        self._setup_ui()
        self._setup_menu()
        self._setup_statusbar()

    def _setup_menu(self):
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")
        settings_action = QAction("⚙ Settings", self)
        settings_action.triggered.connect(self._show_settings)
        file_menu.addAction(settings_action)
        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Help menu
        help_menu = menubar.addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_statusbar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready — Select a folder to begin")

    def _setup_ui(self):
        try:
            from gui.widgets.animated_background import AnimatedBackground
            central = AnimatedBackground()
        except ImportError:
            central = QWidget()
            
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(24, 16, 24, 16)
        main_layout.setSpacing(12)

        # Header
        self.header = AppHeader()
        main_layout.addWidget(self.header)

        # Step indicator
        self.step_indicator = QWidget()
        step_layout = QHBoxLayout(self.step_indicator)
        step_layout.setContentsMargins(0, 0, 0, 0)
        self.step_labels = []
        steps = ["① Select Folder", "② Preview", "③ Processing", "④ Results"]
        for i, text in enumerate(steps):
            lbl = QPushButton(text)
            lbl.setEnabled(False)
            lbl.setFlat(True)
            lbl.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    color: #4b5563;
                    font-weight: bold;
                    font-size: 13px;
                    padding: 6px 12px;
                }
                QPushButton:disabled {
                    color: #4b5563;
                }
            """)
            step_layout.addWidget(lbl)
            self.step_labels.append(lbl)
        self._highlight_step(0)
        main_layout.addWidget(self.step_indicator)

        # Stacked widget for steps
        self.stack = QStackedWidget()

        # ─── Step 1: Input ───
        step1 = QWidget()
        s1_layout = QVBoxLayout(step1)
        s1_layout.setSpacing(16)

        self.folder_picker = FolderPicker()
        self.folder_picker.path_changed.connect(self._on_path_changed)
        
        self.series_input = SeriesInput()
        
        self.watch_cb = QCheckBox("👀 Enable Watch Folder (Auto-scan on new files)")
        self.watch_cb.setStyleSheet("font-weight: bold; color: #a5b4fc;")
        self.watch_cb.toggled.connect(self._toggle_watcher)
        self.watcher = None

        self.scan_btn = QPushButton("🔍  Scan Folder")
        self.scan_btn.setObjectName("primaryButton")
        self.scan_btn.setFixedHeight(44)
        self.scan_btn.setFixedWidth(240)
        self.scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scan_btn.clicked.connect(self._run_scan)

        s1_layout.addStretch(1)
        s1_layout.addWidget(self.folder_picker)
        s1_layout.addWidget(self.series_input)
        s1_layout.addSpacing(10)
        s1_layout.addWidget(self.watch_cb, 0, Qt.AlignmentFlag.AlignCenter)
        s1_layout.addWidget(self.scan_btn, 0, Qt.AlignmentFlag.AlignCenter)
        s1_layout.addStretch(2)

        # ─── Step 2: Preview ───
        step2 = QWidget()
        s2_layout = QVBoxLayout(step2)
        s2_layout.setSpacing(12)

        self.preview_panel = PreviewPanel()
        self.options_panel = OptionsPanel()

        nav2 = QHBoxLayout()
        back2_btn = QPushButton("← Back")
        back2_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back2_btn.clicked.connect(lambda: self._go_to_step(0))
        self.process_btn = QPushButton("▶  Start Processing")
        self.process_btn.setObjectName("primaryButton")
        self.process_btn.setFixedHeight(42)
        self.process_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.process_btn.clicked.connect(self._start_processing)
        nav2.addWidget(back2_btn)
        nav2.addStretch()
        nav2.addWidget(self.process_btn)

        s2_layout.addWidget(self.preview_panel, 1)
        s2_layout.addWidget(self.options_panel)
        s2_layout.addLayout(nav2)

        # ─── Step 3: Processing ───
        step3 = QWidget()
        s3_layout = QVBoxLayout(step3)
        s3_layout.setSpacing(12)

        self.progress_panel = ProgressPanel()
        self.log_panel = LogPanel()

        s3_layout.addWidget(self.progress_panel)
        s3_layout.addWidget(self.log_panel, 1)

        # ─── Step 4: Results ───
        step4 = QWidget()
        s4_layout = QVBoxLayout(step4)

        self.results_panel = ResultsPanel()
        self.results_panel.process_another_requested.connect(lambda: self._go_to_step(0))
        self.results_panel.open_folder_requested.connect(self._open_output_folder)

        s4_layout.addWidget(self.results_panel)

        # Add steps to stack
        self.stack.addWidget(step1)
        self.stack.addWidget(step2)
        self.stack.addWidget(step3)
        self.stack.addWidget(step4)

        main_layout.addWidget(self.stack, 1)

    def _highlight_step(self, step_index: int):
        """Highlight current step in the step indicator."""
        for i, lbl in enumerate(self.step_labels):
            if i == step_index:
                lbl.setStyleSheet("""
                    QPushButton {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 #6366f1, stop:1 #8b5cf6);
                        border: none;
                        border-radius: 6px;
                        color: white;
                        font-weight: bold;
                        font-size: 13px;
                        padding: 6px 12px;
                    }
                """)
            elif i < step_index:
                lbl.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        border: none;
                        color: #10b981;
                        font-weight: bold;
                        font-size: 13px;
                        padding: 6px 12px;
                    }
                """)
            else:
                lbl.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        border: none;
                        color: #4b5563;
                        font-weight: bold;
                        font-size: 13px;
                        padding: 6px 12px;
                    }
                """)

    def _go_to_step(self, step: int):
        self.stack.setCurrentIndex(step)
        self._highlight_step(step)

    # ─── Step 1: Scan ───

    def _on_path_changed(self, new_path: str):
        if self.watch_cb.isChecked():
            self.watch_cb.setChecked(False)

    def _toggle_watcher(self, checked: bool):
        try:
            from core.watcher import FolderWatcher
        except ImportError:
            QMessageBox.warning(self, "Error", "Watchdog module not installed. Run 'pip install watchdog'.")
            self.watch_cb.setChecked(False)
            return

        if checked:
            path = self.folder_picker.get_path()
            if not path:
                QMessageBox.warning(self, "Warning", "Please select a folder to watch first.")
                self.watch_cb.setChecked(False)
                return
            
            if self.watcher is not None:
                self.watcher.stop()
            
            self.watcher = FolderWatcher(path)
            self.watcher.folder_changed.connect(self._run_scan)
            self.watcher.start()
            self.status_bar.showMessage(f"Watching folder for changes: {path}")
        else:
            if self.watcher is not None:
                self.watcher.stop()
                self.watcher = None
                self.status_bar.showMessage("Stopped watching folder.")

    def _run_scan(self):
        # Prevent watch folder from interrupting an active processing session
        if self.stack.currentIndex() >= 2:
            return

        path = self.folder_picker.get_path()
        if not path:
            QMessageBox.warning(self, "Warning", "Please select a folder first.")
            return

        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("⏳ Scanning...")
        self.status_bar.showMessage("Scanning folder...")

        series = self.series_input.get_series_name()

        self._scan_worker = ScanWorker(path, series)
        self._scan_worker.completed.connect(self._on_scan_completed)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

    def _on_scan_completed(self, result):
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("🔍  Scan Folder")
        self.scan_result = result

        match_count = len(result.matches)
        self.status_bar.showMessage(f"Scan complete — {match_count} episodes matched")

        if match_count == 0:
            QMessageBox.information(
                self, "No Videos Found",
                "No video files were found in the selected folder. Check that your folder "
                "contains valid video files (.mkv)."
            )
            return

        # Auto-fill series name if detected
        if result.series_name and not self.series_input.get_series_name():
            self.series_input.set_series_name(result.series_name)

        self.preview_panel.populate(result)
        self._go_to_step(1)

    def _on_scan_error(self, err):
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("🔍  Scan Folder")
        self.status_bar.showMessage("Scan failed")
        QMessageBox.critical(self, "Scan Error", f"Failed to scan folder:\n\n{err}")

    # ─── Step 2: Process ───

    def _start_processing(self):
        if not self.scan_result:
            return

        options = self.options_panel.get_options()
        if not options:
            options = ProcessingOptions() if ProcessingOptions else None

        self._go_to_step(2)
        self.progress_panel.reset()
        self.log_panel.clear()
        self.status_bar.showMessage("Processing...")

        self._process_worker = ProcessWorker(self.scan_result, options)
        self._process_worker.progress_updated.connect(
            lambda cur, total, fname: self.progress_panel.update_progress(cur, total, fname)
        )
        self._process_worker.log_message.connect(self.log_panel.append_log)
        self._process_worker.completed.connect(self._on_processing_completed)
        self._process_worker.error.connect(self._on_processing_error)
        self._process_worker.start()

    def _on_processing_completed(self, result):
        self.status_bar.showMessage("Processing complete!")
        self.results_panel.show_results(result)
        self._go_to_step(3)

    def _on_processing_error(self, err):
        self.status_bar.showMessage("Processing failed")
        QMessageBox.critical(self, "Processing Error", f"Processing failed:\n\n{err}")
        self._go_to_step(1)

    # ─── Dialogs ───

    def _show_settings(self):
        if self.config:
            dlg = SettingsDialog(self.config, self)
            dlg.exec()

    def _show_about(self):
        dlg = AboutDialog(self)
        dlg.exec()

    def _open_output_folder(self):
        import os
        import subprocess
        from pathlib import Path
        
        if not self.scan_result or not self.scan_result.folder_path:
            return
            
        base_folder = Path(self.scan_result.folder_path)
        
        # Check if we have an output_dir from options (which we do if they process)
        # OptionsPanel has `get_options()`, wait, let's just get the one we used for the process worker
        # if the process_worker has options... we didn't save options to the class instance.
        # But we can just grab current options from the panel.
        
        options = self.options_panel.get_options()
        output_folder = base_folder
        
        if options and options.output_dir:
            output_folder = Path(options.output_dir)
            
        if not output_folder.exists():
            output_folder = base_folder
            
        path_str = str(output_folder)
        try:
            if sys.platform == 'win32':
                os.startfile(path_str)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', path_str])
            else:
                subprocess.Popen(['xdg-open', path_str])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open folder:\n{e}")



def main():
    """Launch the GUI application."""
    import ctypes
    import os
    from PySide6.QtGui import QIcon

    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # Cross-platform consistent style

    # Ensure Windows uses our custom icon in the taskbar
    if sys.platform == 'win32':
        myappid = 'animesubtool.fluid.v3'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    
    # Resolve the path to the bundled icon
    if hasattr(sys, '_MEIPASS'):
        icon_path = os.path.join(sys._MEIPASS, 'app_icon.ico')
    else:
        # Running from source, icon is in root folder
        base_dir = Path(__file__).resolve().parent.parent
        icon_path = str(base_dir / 'app_icon.ico')
    
    app.setWindowIcon(QIcon(icon_path))

    window = AnimeSubToolApp()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
