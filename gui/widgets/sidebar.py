"""Left sidebar: logo, step navigation and the settings/about links."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout

from gui.theme import Colors, add_glow


class Sidebar(QFrame):
    settings_requested = Signal()
    about_requested = Signal()

    STEPS = ["SELECT", "PREVIEW", "PROCESS", "RESULTS"]

    def __init__(self, version: str, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(210)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 26, 0, 18)
        layout.setSpacing(0)

        logo = QLabel(
            f"<span style='color:{Colors.blue_bright}'>ANIME</span>"
            f"<span style='color:{Colors.red}'>//</span>"
            f"<span style='color:{Colors.text}'>SUB</span>"
        )
        logo.setTextFormat(Qt.TextFormat.RichText)
        logo.setStyleSheet("font-size: 24px; font-weight: 900; letter-spacing: 2px;"
                           " background: transparent; padding-left: 20px;")
        add_glow(logo, Colors.blue, 18)

        tagline = QLabel("MERGE · SYNC · CLEAN")
        tagline.setProperty("role", "fieldLabel")
        tagline.setStyleSheet(f"padding-left: 22px; color: {Colors.text_muted}; font-size: 9px;")

        layout.addWidget(logo)
        layout.addSpacing(2)
        layout.addWidget(tagline)
        layout.addSpacing(34)

        self._buttons: list[QPushButton] = []
        for i, name in enumerate(self.STEPS, start=1):
            btn = QPushButton(f"{i:02d}   {name}")
            btn.setObjectName("navButton")
            btn.setEnabled(False)  # navigation is driven by the workflow, not clicks
            layout.addWidget(btn)
            self._buttons.append(btn)

        layout.addStretch(1)

        for text, signal in (("⚙  Settings", self.settings_requested),
                             ("ⓘ  About", self.about_requested)):
            link = QPushButton(text)
            link.setObjectName("linkButton")
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.clicked.connect(signal.emit)
            link.setStyleSheet("margin-left: 16px;")
            layout.addWidget(link)

        ver = QLabel(f"v{version}")
        ver.setProperty("role", "hint")
        ver.setStyleSheet("padding: 10px 0 0 21px;")
        layout.addWidget(ver)

        self.set_step(0)

    def set_step(self, index: int):
        for i, (btn, name) in enumerate(zip(self._buttons, self.STEPS)):
            state = "active" if i == index else "done" if i < index else "pending"
            prefix = " ✓" if state == "done" else f"{i + 1:02d}"
            btn.setText(f"{prefix}   {name}")
            btn.setProperty("state", state)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
