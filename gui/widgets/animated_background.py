"""
Neon grid background.

Black base, a faint blue perspective-free grid, two slow glows (blue and red)
drifting in opposite corners, and a thin scan line sweeping down. Pure QPainter,
30 FPS, no image or video assets.
"""

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

GRID_STEP = 36
FPS = 30


class AnimatedBackground(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self._t = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000 // FPS)

    def _tick(self):
        self._t += 1.0 / FPS
        self.update()

    def _glow(self, painter: QPainter, cx: float, cy: float, r: float, color: QColor):
        grad = QRadialGradient(QPointF(cx, cy), r)
        edge = QColor(color)
        edge.setAlpha(0)
        grad.setColorAt(0.0, color)
        grad.setColorAt(1.0, edge)
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

    def paintEvent(self, event):
        w, h, t = self.width(), self.height(), self._t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        p.fillRect(self.rect(), QColor(4, 6, 10))

        # Drifting glows: blue top-right, red bottom-left
        size = (w + h) * 0.32
        self._glow(p, w * 0.82 + math.sin(t * 0.25) * w * 0.08,
                   h * 0.18 + math.cos(t * 0.21) * h * 0.08, size, QColor(0, 140, 255, 60))
        self._glow(p, w * 0.18 + math.cos(t * 0.19) * w * 0.08,
                   h * 0.86 + math.sin(t * 0.23) * h * 0.06, size * 0.9, QColor(255, 30, 70, 42))

        # Grid
        p.setPen(QPen(QColor(0, 160, 255, 14), 1))
        offset = (t * 6) % GRID_STEP
        x = -offset
        while x < w:
            p.drawLine(QPointF(x, 0), QPointF(x, h))
            x += GRID_STEP
        y = offset
        while y < h:
            p.drawLine(QPointF(0, y), QPointF(w, y))
            y += GRID_STEP

        # Scan line
        scan_y = (t * 70) % (h + 200) - 100
        band = QLinearGradient(0, scan_y - 60, 0, scan_y)
        band.setColorAt(0.0, QColor(0, 183, 255, 0))
        band.setColorAt(1.0, QColor(0, 183, 255, 18))
        p.fillRect(QRectF(0, scan_y - 60, w, 60), QBrush(band))
        p.setPen(QPen(QColor(0, 200, 255, 50), 1))
        p.drawLine(QPointF(0, scan_y), QPointF(w, scan_y))

        # Vignette so content in the middle stays readable
        vignette = QRadialGradient(QPointF(w / 2, h / 2), max(w, h) * 0.75)
        vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
        vignette.setColorAt(1.0, QColor(0, 0, 0, 150))
        p.fillRect(self.rect(), QBrush(vignette))
        p.end()
