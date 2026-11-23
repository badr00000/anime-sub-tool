"""Progress Panel — overall progress, the episode being merged, and time left."""

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from gui.theme import Colors


class ProgressPanel(QFrame):
    """Public API: update_progress(), reset(), cancel_requested, cancel_btn."""

    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(16)
        self.percent_label = QLabel("0%")
        self.percent_label.setStyleSheet(f"font-family: {Colors.font_mono}; font-size: 32px;"
                                         f" font-weight: 500; color: {Colors.text}; background: transparent;")
        self.file_label = QLabel("Preparing")
        self.file_label.setTextFormat(Qt.TextFormat.PlainText)
        self.file_label.setProperty("role", "fieldLabel")

        times = QVBoxLayout()
        times.setSpacing(4)
        self.speed_label = QLabel("Elapsed 00:00")
        self.eta_label = QLabel("Time left —")
        for lbl in (self.speed_label, self.eta_label):
            lbl.setProperty("role", "mono")
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            times.addWidget(lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.addWidget(self.percent_label)
        title_col.addWidget(self.file_label)
        top.addLayout(title_col)
        top.addStretch()
        top.addLayout(times)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)

        actions = QHBoxLayout()
        actions.addStretch()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("dangerButton")
        self.cancel_btn.setFixedHeight(36)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        actions.addWidget(self.cancel_btn)

        self._started = time.monotonic()
        layout.addLayout(top)
        layout.addWidget(self.bar)
        layout.addLayout(actions)

    @staticmethod
    def _clock(seconds: float) -> str:
        seconds = int(max(0, seconds))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def update_progress(self, current: int, total: int, file_name: str = "",
                        speed: str = "", eta: str = ""):
        self.file_label.setText(file_name or "Merging")
        pct = min(int(current * 100 / total), 100) if total > 0 else 0
        self.percent_label.setText(f"{pct}%")
        self.bar.setValue(pct)

        # Elapsed / remaining are computed here unless the caller supplies them
        elapsed = time.monotonic() - self._started
        self.speed_label.setText(f"Elapsed {speed or self._clock(elapsed)}")
        if eta:
            self.eta_label.setText(f"Time left {eta}")
        elif 0 < pct < 100:
            self.eta_label.setText(f"Time left {self._clock(elapsed * (100 - pct) / pct)}")
        elif pct >= 100:
            self.eta_label.setText("Time left 00:00")

    def reset(self):
        self._started = time.monotonic()
        self.percent_label.setText("0%")
        self.bar.setValue(0)
        self.file_label.setText("Preparing")
        self.speed_label.setText("Elapsed 00:00")
        self.eta_label.setText("Time left —")
