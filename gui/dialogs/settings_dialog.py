"""Settings Dialog — Application preferences."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QFileDialog, QGroupBox, QFormLayout
)
from PySide6.QtCore import Qt

try:
    from core.models import AppConfig
    from core.config import save_config
except ImportError:
    AppConfig = None
    save_config = None


class SettingsDialog(QDialog):
    """Application settings dialog."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings")
        self.setFixedSize(500, 400)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Title
        title = QLabel("Settings")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #00b7ff; letter-spacing: 2px;")
        layout.addWidget(title)

        # MKVToolNix section
        mkv_group = QGroupBox("MKVToolNix")
        mkv_layout = QHBoxLayout(mkv_group)

        self.mkv_path_edit = QLineEdit(config.mkvtoolnix_path if config else "")
        self.mkv_path_edit.setPlaceholderText("Path to MKVToolNix directory...")
        mkv_browse = QPushButton("Browse")
        mkv_browse.setFixedWidth(80)
        mkv_browse.clicked.connect(self._browse_mkv)

        mkv_layout.addWidget(self.mkv_path_edit, 1)
        mkv_layout.addWidget(mkv_browse)

        # Processing section
        proc_group = QGroupBox("Processing Defaults")
        proc_layout = QFormLayout(proc_group)

        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 8)
        self.workers_spin.setValue(config.default_workers if config else 4)
        proc_layout.addRow("Default workers:", self.workers_spin)

        self.subfolder_edit = QLineEdit(config.output_subfolder if config else "PROCESSED")
        proc_layout.addRow("Output subfolder:", self.subfolder_edit)

        self.sub_lang_edit = QLineEdit(config.subtitle_language if config else "ara")
        proc_layout.addRow("Subtitle language:", self.sub_lang_edit)

        self.sub_name_edit = QLineEdit(config.subtitle_name if config else "Arabic")
        proc_layout.addRow("Subtitle name:", self.sub_name_edit)

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
        if self.config and save_config:
            self.config.mkvtoolnix_path = self.mkv_path_edit.text()
            self.config.default_workers = self.workers_spin.value()
            self.config.output_subfolder = self.subfolder_edit.text()
            self.config.subtitle_language = self.sub_lang_edit.text()
            self.config.subtitle_name = self.sub_name_edit.text()
            save_config(self.config)
        self.accept()
