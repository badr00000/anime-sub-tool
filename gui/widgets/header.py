"""App Header — Gradient title with subtle branding."""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout
from PySide6.QtCore import Qt


class AppHeader(QWidget):
    """Application header with gradient title and version badge."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("appHeader")
        self.setFixedHeight(70)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Left side: Title
        left = QVBoxLayout()
        left.setSpacing(2)

        title = QLabel("Anime Subtitle Automation")
        title.setStyleSheet("""
            QLabel {
                font-size: 22px;
                font-weight: 800;
                color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #a5b4fc, stop:0.5 #c4b5fd, stop:1 #f0abfc);
                background: transparent;
                letter-spacing: 0.5px;
            }
        """)

        subtitle = QLabel("Smart MKV processing  \u2022  Subtitle embedding  \u2022  Audio filtering")
        subtitle.setStyleSheet("""
            QLabel {
                font-size: 11px;
                color: #64748b;
                background: transparent;
                letter-spacing: 0.3px;
            }
        """)

        left.addWidget(title)
        left.addWidget(subtitle)

        # Right side: Version badge
        version_badge = QLabel("v2.0")
        version_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_badge.setFixedSize(52, 28)
        version_badge.setStyleSheet("""
            QLabel {
                background-color: rgba(99, 102, 241, 0.15);
                border: 1px solid rgba(99, 102, 241, 0.3);
                border-radius: 14px;
                color: #a5b4fc;
                font-size: 11px;
                font-weight: 700;
            }
        """)

        layout.addLayout(left, 1)
        layout.addWidget(version_badge, 0, Qt.AlignmentFlag.AlignTop)
