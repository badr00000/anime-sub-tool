"""Left sidebar: logo, the two tools (merge season / sync subtitle), and settings/about links."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout

from gui.theme import Colors, add_glow


class Sidebar(QFrame):
    settings_requested = Signal()
    about_requested = Signal()
    mode_requested = Signal(str)   # "merge" or "sync"

    STEPS = ["SELECT", "PREVIEW", "PROCESS", "RESULTS"]

    def __init__(self, version: str, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(210)
        self._step = 0
        self._mode = "merge"

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
        layout.addSpacing(30)

        # Tool 1: merge a season (a 4-step wizard)
        self.merge_btn = self._mode_button("▣  MERGE SEASON", "merge")
        layout.addWidget(self.merge_btn)
        layout.addSpacing(4)

        self._buttons: list[QPushButton] = []
        for i, name in enumerate(self.STEPS, start=1):
            btn = QPushButton(f"{i:02d}   {name}")
            btn.setObjectName("navButton")
            btn.setEnabled(False)  # driven by the workflow, not by clicks
            layout.addWidget(btn)
            self._buttons.append(btn)

        # Tool 2: sync one subtitle (standalone)
        layout.addSpacing(22)
        self.sync_btn = self._mode_button("◷  SYNC SUBTITLE", "sync")
        layout.addWidget(self.sync_btn)

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

        self._render()

    def _mode_button(self, text: str, mode: str) -> QPushButton:
        b = QPushButton(text)
        b.setObjectName("modeButton")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda: self.mode_requested.emit(mode))
        return b

    def set_step(self, index: int):
        self._step = index
        self._render()

    def set_mode(self, mode: str):
        self._mode = mode
        self._render()

    def _render(self):
        for btn, mode in ((self.merge_btn, "merge"), (self.sync_btn, "sync")):
            btn.setProperty("active", "true" if self._mode == mode else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        for i, (btn, name) in enumerate(zip(self._buttons, self.STEPS)):
            if i < self._step:
                state = "done"
            elif i == self._step:
                state = "active" if self._mode == "merge" else "paused"
            else:
                state = "pending"
            prefix = " ✓" if state == "done" else f"{i + 1:02d}"
            btn.setText(f"{prefix}   {name}")
            btn.setProperty("state", state)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
