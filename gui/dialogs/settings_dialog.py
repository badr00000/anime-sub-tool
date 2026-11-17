"""Settings Dialog — Application preferences."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QFileDialog, QGroupBox, QFormLayout
)

from core.config import save_config, valid_subfolder_name
from core.constants import MAX_PARALLEL_WORKERS, MIN_PARALLEL_WORKERS
from core.languages import name_of
from core.mkvtools import has_mkvmerge
from core.models import AppConfig
from gui.dialogs import messages
from gui.theme import Colors
from gui.widgets.language_picker import LanguageCombo
from gui.widgets.options_panel import _follow_language


class SettingsDialog(QDialog):
    """Application settings dialog. Edits and saves the AppConfig it is given."""

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings")
        self.setFixedSize(500, 430)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Title
        title = QLabel("Settings")
        title.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {Colors.blue}; letter-spacing: 2px;")
        layout.addWidget(title)

        # MKVToolNix section
        mkv_group = QGroupBox("MKVToolNix")
        mkv_box = QVBoxLayout(mkv_group)
        mkv_layout = QHBoxLayout()

        self.mkv_path_edit = QLineEdit(config.mkvtoolnix_path)
        self.mkv_path_edit.setPlaceholderText("Empty = use the bundled mkvmerge")
        self.mkv_path_edit.setClearButtonEnabled(True)
        mkv_browse = QPushButton("Browse")
        mkv_browse.setFixedWidth(80)
        mkv_browse.clicked.connect(self._browse_mkv)

        mkv_layout.addWidget(self.mkv_path_edit, 1)
        mkv_layout.addWidget(mkv_browse)
        mkv_hint = QLabel("Leave empty to use the copy that comes with the app. "
                          "Set a folder only to use your own MKVToolNix installation.")
        mkv_hint.setProperty("role", "hint")
        mkv_hint.setWordWrap(True)
        mkv_box.addLayout(mkv_layout)
        mkv_box.addWidget(mkv_hint)

        # Processing section
        proc_group = QGroupBox("Processing Defaults")
        proc_layout = QFormLayout(proc_group)

        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(MIN_PARALLEL_WORKERS, MAX_PARALLEL_WORKERS)
        self.workers_spin.setValue(config.default_workers)
        proc_layout.addRow("Episodes at once:", self.workers_spin)

        self.subfolder_edit = QLineEdit(config.output_subfolder)
        proc_layout.addRow("Output subfolder:", self.subfolder_edit)

        self.sub_lang_edit = LanguageCombo()
        self.sub_lang_edit.set_value(config.subtitle_language)
        proc_layout.addRow("Default subtitle language:", self.sub_lang_edit)

        self.sub_name_edit = QLineEdit(config.subtitle_name)
        proc_layout.addRow("Subtitle name:", self.sub_name_edit)
        _follow_language(self.sub_lang_edit, self.sub_name_edit)

        # Buttons
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save Settings")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self._save)

        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)

        layout.addWidget(mkv_group)
        layout.addWidget(proc_group)
        layout.addStretch()
        layout.addLayout(btn_layout)

    def _browse_mkv(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select MKVToolNix Directory", self.mkv_path_edit.text()
        )
        if folder:
            self.mkv_path_edit.setText(folder)

    def _save(self):
        mkv_path = self.mkv_path_edit.text().strip()
        subfolder = self.subfolder_edit.text().strip()

        if mkv_path and not has_mkvmerge(mkv_path):
            messages.warn(self, "MKVToolNix",
                          f"There is no mkvmerge in this folder:\n\n{mkv_path}\n\n"
                          "Pick the folder that contains it, or leave the field empty "
                          "to use the bundled copy.")
            return
        if not valid_subfolder_name(subfolder):
            messages.warn(self, "Output subfolder",
                          "The output subfolder must be a plain folder name "
                          "(no \\ / : * ? \" < > | and not '..').")
            return

        language = self.sub_lang_edit.value() or "ara"
        self.config.mkvtoolnix_path = mkv_path
        self.config.default_workers = self.workers_spin.value()
        self.config.output_subfolder = subfolder
        self.config.subtitle_language = language
        self.config.subtitle_name = self.sub_name_edit.text().strip() or name_of(language)
        if not save_config(self.config):
            messages.warn(self, "Settings", "The settings could not be written to disk. "
                                            "They apply until the app is closed.")
        self.accept()
