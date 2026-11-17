"""Progress Panel — neon progress ring with the current episode and stats."""

import time

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QConicalGradient, QFont, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from gui.theme import Colors


class ProgressRing(QWidget):
    """Circular progress: dim track, blue→red sweep, percentage in the middle."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self.setFixedSize(230, 230)

    def set_value(self, value: int):
        self._value = max(0, min(100, int(value)))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        margin = 18
        rect = QRectF(margin, margin, self.width() - 2 * margin, self.height() - 2 * margin)

        # Tick marks around the ring
        p.save()
        p.translate(self.width() / 2, self.height() / 2)
        tick_pen = QPen(QColor(Colors.border_hover), 1.2)
        for i in range(60):
            p.setPen(tick_pen if i * 100 / 60 > self._value else QPen(QColor(0, 183, 255, 110), 1.2))
            p.drawLine(0, -self.height() / 2 + 3, 0, -self.height() / 2 + 8)
            p.rotate(6)
        p.restore()

        # Track
        p.setPen(QPen(QColor(Colors.border), 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        p.drawArc(rect, 0, 360 * 16)

        # Sweep (starts at 12 o'clock, clockwise)
        if self._value > 0:
            grad = QConicalGradient(rect.center(), 90)
            grad.setColorAt(0.0, QColor(Colors.blue_bright))
            grad.setColorAt(0.6, QColor(Colors.blue))
            grad.setColorAt(1.0, QColor(Colors.red))
            # Outer glow pass then the sharp arc
            glow = QPen(QColor(0, 183, 255, 45), 22, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap)
            p.setPen(glow)
            p.drawArc(rect, 90 * 16, int(-self._value * 3.6 * 16))
            p.setPen(QPen(grad, 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            p.drawArc(rect, 90 * 16, int(-self._value * 3.6 * 16))

        # Number
        p.setPen(QColor(Colors.text))
        f = QFont("Segoe UI", 38)
        f.setWeight(QFont.Weight.Black)
        p.setFont(f)
        p.drawText(rect.adjusted(0, -12, 0, -12), Qt.AlignmentFlag.AlignCenter, f"{self._value}")
        f2 = QFont("Consolas", 10)
        f2.setBold(True)
        f2.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
        p.setFont(f2)
        p.setPen(QColor(Colors.blue))
        p.drawText(rect.adjusted(0, 58, 0, 0), Qt.AlignmentFlag.AlignCenter, "PERCENT")
        p.end()


class ProgressPanel(QWidget):
    """Displays processing progress. Public API: update_progress(), reset(), cancel_requested."""

    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("progressPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.ring = ProgressRing()

        self.file_label = QLabel("Preparing...")
        self.file_label.setTextFormat(Qt.TextFormat.PlainText)
        self.file_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.file_label.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {Colors.text};"
                                      " letter-spacing: 1px; background: transparent;")

        stats = QHBoxLayout()
        self.speed_label = QLabel("SPEED  --")
        self.eta_label = QLabel("ETA  --")
        for lbl in (self.speed_label, self.eta_label):
            lbl.setProperty("role", "fieldLabel")
            lbl.setStyleSheet(f"color: {Colors.text_muted};")
        stats.addStretch()
        stats.addWidget(self.speed_label)
        stats.addSpacing(30)
        stats.addWidget(self.eta_label)
        stats.addStretch()

        self.cancel_btn = QPushButton("CANCEL")
        self.cancel_btn.setObjectName("dangerButton")
        self.cancel_btn.setFixedSize(160, 36)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)

        self._started = time.monotonic()
        layout.addWidget(self.ring, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.file_label)
        layout.addLayout(stats)
        layout.addSpacing(4)
        layout.addWidget(self.cancel_btn, 0, Qt.AlignmentFlag.AlignCenter)

    @staticmethod
    def _clock(seconds: float) -> str:
        seconds = int(max(0, seconds))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def update_progress(self, current: int, total: int, file_name: str = "",
                        speed: str = "", eta: str = ""):
        self.file_label.setText(f"PROCESSING  ·  {file_name.upper()}" if file_name else "PROCESSING")
        pct = min(int(current * 100 / total), 100) if total > 0 else 0
        self.ring.set_value(pct)

        # Elapsed / remaining are computed here unless the caller supplies them
        elapsed = time.monotonic() - self._started
        self.speed_label.setText(f"ELAPSED  {speed or self._clock(elapsed)}")
        if eta:
            self.eta_label.setText(f"ETA  {eta}")
        elif 0 < pct < 100:
            self.eta_label.setText(f"ETA  {self._clock(elapsed * (100 - pct) / pct)}")
        elif pct >= 100:
            self.eta_label.setText("ETA  00:00")

    def reset(self):
        self._started = time.monotonic()
        self.ring.set_value(0)
        self.file_label.setText("PREPARING...")
        self.speed_label.setText("ELAPSED  00:00")
        self.eta_label.setText("ETA  --")
