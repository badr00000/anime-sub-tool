"""About Dialog — Application information and credits."""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

try:
    from core.constants import APP_NAME, APP_VERSION
except ImportError:
    APP_NAME = "Anime Subtitle Automation Tool"
    APP_VERSION = "2.0.0"


class AboutDialog(QDialog):
    """Application about dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setFixedSize(450, 300)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(30, 30, 30, 30)

        # Title
        title = QLabel(APP_NAME)
        title.setStyleSheet("""
            font-size: 24px;
            font-weight: 800;
            color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #5fd6ff, stop:1 #ff2b4e);
        """)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Version
        version = QLabel(f"Version {APP_VERSION}")
        version.setStyleSheet("font-size: 14px; color: #00b7ff; font-weight: bold;")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Description
        desc = QLabel(
            "An intelligent automation tool for matching, embedding,\n"
            "and standardizing anime subtitles and audio tracks.\n\n"
            "Powered by MKVToolNix, Anitopy, and PySide6."
        )
        desc.setStyleSheet("font-size: 13px; color: #9db0c6; line-height: 1.5;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Author / Credits
        credits = QLabel("Designed for AI Development Team Workflow")
        credits.setStyleSheet("font-size: 12px; color: #55667c; font-style: italic;")
        credits.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Button
        btn_layout = QHBoxLayout()
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(120)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(version)
        layout.addSpacing(10)
        layout.addWidget(desc)
        layout.addStretch()
        layout.addWidget(credits)
        layout.addSpacing(10)
        layout.addLayout(btn_layout)
