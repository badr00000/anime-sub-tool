"""About Dialog — Application information, credits and third-party licences."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPlainTextEdit, QPushButton, QHBoxLayout,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from core.constants import APP_NAME, APP_VERSION
from gui.theme import Colors
from utils.paths import resource_path

# Shipped next to the app (repo root from source, bundle root in the .exe):
# the app's own licence first, then the third-party notices and the GPLv2 text.
LICENSE_FILES = ("LICENSE", "THIRD_PARTY_LICENSES.md", "licenses/GPL-2.0.txt")


def load_license_text() -> str:
    """The app's own licence, the third-party notices and the full GPLv2 text,
    as plain text."""
    parts = []
    for name in LICENSE_FILES:
        path = resource_path(*name.split("/"))
        try:
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            parts.append(f"[{name} is missing from this copy of the application.]")
    return ("\n\n" + "=" * 72 + "\n\n").join(parts)


class LicensesDialog(QDialog):
    """Read-only view of the licence texts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Licenses")
        self.resize(720, 560)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(QFont("Consolas", 9))
        self.text.setPlainText(load_license_text())

        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(120)
        close_btn.clicked.connect(self.accept)

        layout.addWidget(self.text, 1)
        layout.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignRight)


class AboutDialog(QDialog):
    """Application about dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setFixedSize(450, 320)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(32, 32, 32, 32)

        # Title
        title = QLabel(APP_NAME)
        title.setStyleSheet(f"font-size: 20px; font-weight: 600; color: {Colors.text};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)

        # Version
        version = QLabel(f"Version {APP_VERSION}")
        version.setStyleSheet(f"font-family: {Colors.font_mono}; font-size: 12px; color: {Colors.text_muted};")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Description
        desc = QLabel(
            "Matches anime episodes with their subtitle files, merges them\n"
            "with mkvmerge and cleans up audio and subtitle tracks.\n\n"
            "Uses MKVToolNix (GPLv2), Qt / PySide6 (LGPLv3), anitopy,\n"
            "RapidFuzz, click and watchdog."
        )
        desc.setStyleSheet(f"font-size: 13px; color: {Colors.text_secondary};")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Buttons
        btn_layout = QHBoxLayout()
        self.licenses_btn = QPushButton("Licenses")
        self.licenses_btn.setFixedWidth(120)
        self.licenses_btn.clicked.connect(self._show_licenses)
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(120)
        close_btn.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(self.licenses_btn)
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()

        layout.addWidget(title)
        layout.addWidget(version)
        layout.addSpacing(10)
        layout.addWidget(desc)
        layout.addStretch()
        layout.addLayout(btn_layout)

    def _show_licenses(self):
        LicensesDialog(self).exec()
