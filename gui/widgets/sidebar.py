"""Left sidebar: logo, the two tools (merge season / sync subtitle), and settings/about links."""

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from gui.icons import icon
from gui.theme import Colors

ICON = QSize(16, 16)


def _logo_mark(size: int = 22) -> QPixmap:
    """A flat mark: a frame of video with two subtitle lines at the bottom."""
    ratio = 2.0
    px = QPixmap(int(size * ratio), int(size * ratio))
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(ratio, ratio)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(Colors.accent))
    p.drawRoundedRect(QRectF(0, 0, size, size), 6, 6)
    p.setBrush(QColor(Colors.accent_text))
    p.drawRoundedRect(QRectF(5, size - 9, size - 10, 2), 1, 1)
    p.drawRoundedRect(QRectF(8, size - 5.5, size - 16, 2), 1, 1)
    p.end()
    px.setDevicePixelRatio(ratio)
    return px


class Sidebar(QFrame):
    settings_requested = Signal()
    about_requested = Signal()
    mode_requested = Signal(str)   # "merge" or "sync"

    STEPS = ["Choose folder", "Check pairs", "Merge", "Results"]

    def __init__(self, version: str, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(240)
        self._step = 0
        self._mode = "merge"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 20, 12, 16)
        layout.setSpacing(2)

        brand = QHBoxLayout()
        brand.setContentsMargins(10, 0, 0, 0)
        brand.setSpacing(10)
        mark = QLabel()
        mark.setPixmap(_logo_mark())
        name = QLabel(f"Anime<span style='color:{Colors.text_muted}'>//</span>Sub")
        name.setTextFormat(Qt.TextFormat.RichText)
        name.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {Colors.text}; background: transparent;")
        brand.addWidget(mark)
        brand.addWidget(name)
        brand.addStretch()
        layout.addLayout(brand)
        layout.addSpacing(24)

        # Tool 1: merge a season (a 4-step wizard)
        self.merge_btn = self._mode_button("Merge season", "layers", "merge")
        layout.addWidget(self.merge_btn)

        self._buttons: list[QPushButton] = []
        for name_text in self.STEPS:
            btn = QPushButton(name_text)
            btn.setObjectName("navButton")
            btn.setIconSize(QSize(12, 12))
            btn.setEnabled(False)  # driven by the workflow, not by clicks
            layout.addWidget(btn)
            self._buttons.append(btn)

        # Tool 2: sync one subtitle (standalone)
        layout.addSpacing(8)
        self.sync_btn = self._mode_button("Sync subtitle", "captions", "sync")
        layout.addWidget(self.sync_btn)

        layout.addStretch(1)

        for text, name_icon, signal in (("Settings", "sliders", self.settings_requested),
                                        ("About", "info", self.about_requested)):
            link = QPushButton(text)
            link.setObjectName("linkButton")
            link.setIcon(icon(name_icon, Colors.text_secondary))
            link.setIconSize(ICON)
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.clicked.connect(signal.emit)
            layout.addWidget(link)

        ver = QLabel(f"Version {version}")
        ver.setProperty("role", "hint")
        ver.setContentsMargins(10, 8, 0, 0)
        layout.addWidget(ver)

        self._render()

    def _mode_button(self, text: str, icon_name: str, mode: str) -> QPushButton:
        b = QPushButton(text)
        b.setObjectName("modeButton")
        b.setIconSize(ICON)
        b.setProperty("iconName", icon_name)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda: self.mode_requested.emit(mode))
        return b

    def set_step(self, index: int):
        self._step = index
        self._render()

    def set_mode(self, mode: str):
        self._mode = mode
        self._render()

    @staticmethod
    def _repolish(widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _render(self):
        for btn, mode in ((self.merge_btn, "merge"), (self.sync_btn, "sync")):
            active = self._mode == mode
            btn.setProperty("active", "true" if active else "false")
            btn.setIcon(icon(btn.property("iconName"), Colors.text if active else Colors.text_secondary))
            self._repolish(btn)

        for i, btn in enumerate(self._buttons):
            if i < self._step:
                state, mark = "done", icon("check", Colors.text_secondary, 12)
            elif i == self._step:
                state = "active" if self._mode == "merge" else "paused"
                mark = icon("dot", Colors.accent if state == "active" else Colors.text_secondary, 12)
            else:
                state, mark = "pending", icon("dot", Colors.hairline_strong, 12)
            btn.setIcon(mark)
            btn.setProperty("state", state)
            self._repolish(btn)
