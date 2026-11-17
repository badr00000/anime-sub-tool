"""Folder Picker — neon drop zone with a path field and browse button."""

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from core.matcher import list_media_files
from gui.theme import Colors


class FolderPicker(QFrame):
    """Drop a folder anywhere on the zone, or type/browse a path.

    Public API (used by the main window): path_changed, get_path(), set_path().
    """

    path_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("folderPicker")
        self.setAcceptDrops(True)
        self.setMinimumHeight(230)
        self._drag_active = False
        self._state = "idle"  # idle | ok | bad

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 30, 36, 26)
        layout.setSpacing(10)

        self.icon = QLabel("⇣")
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setStyleSheet(f"font-size: 40px; color: {Colors.blue}; background: transparent;")

        self.headline = QLabel("DROP YOUR SEASON FOLDER HERE")
        self.headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.headline.setStyleSheet(f"font-size: 16px; font-weight: 800; letter-spacing: 3px;"
                                    f" color: {Colors.text}; background: transparent;")

        hint = QLabel("Episodes (.mkv, .mp4, …) and subtitles (.srt / .ass, …) in the same folder")
        hint.setProperty("role", "hint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("…or paste a folder path")
        self.path_edit.setMinimumHeight(38)
        self.path_edit.textChanged.connect(self._on_text_changed)

        self.browse_btn = QPushButton("BROWSE")
        self.browse_btn.setFixedSize(110, 38)
        self.browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_btn.clicked.connect(self._browse)
        row.addWidget(self.path_edit, 1)
        row.addWidget(self.browse_btn)

        self.status_label = QLabel("")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.icon)
        layout.addWidget(self.headline)
        layout.addWidget(hint)
        layout.addSpacing(8)
        layout.addLayout(row)
        layout.addWidget(self.status_label)

    # ── Painting: dashed neon frame with corner brackets ──
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        color = QColor(Colors.red if self._state == "bad" else Colors.blue)
        fill = QColor(color)
        fill.setAlpha(34 if self._drag_active else 14)
        p.fillRect(r, fill)

        dash = QPen(QColor(color.red(), color.green(), color.blue(), 200 if self._drag_active else 90), 1)
        dash.setDashPattern([6, 5])
        p.setPen(dash)
        p.drawRect(r.adjusted(6, 6, -6, -6))

        # Corner brackets
        p.setPen(QPen(color, 2.5))
        L = 22
        for x, y, dx, dy in ((r.left(), r.top(), 1, 1), (r.right(), r.top(), -1, 1),
                             (r.left(), r.bottom(), 1, -1), (r.right(), r.bottom(), -1, -1)):
            p.drawLine(x, y, x + dx * L, y)
            p.drawLine(x, y, x, y + dy * L)
        p.end()

    def _set_state(self, state: str, message: str = ""):
        self._state = state
        self.status_label.setText(message)
        self.status_label.setProperty("role", {"ok": "ok", "bad": "bad"}.get(state, "hint"))
        self.path_edit.setProperty("state", state if state != "idle" else "")
        for w in (self.status_label, self.path_edit):
            w.style().unpolish(w)
            w.style().polish(w)
        self.update()

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", self.path_edit.text() or "")
        if folder:
            self.path_edit.setText(folder)

    def _on_text_changed(self, text: str):
        path = Path(text.strip()) if text.strip() else None
        if path and path.is_dir():
            # Counted exactly the way the scan will see the folder
            videos, subs = list_media_files(path)
            self._set_state("ok", f"▲ {len(videos)} EPISODE(S)   ·   {len(subs)} SUBTITLE(S) FOUND")
        elif text.strip():
            self._set_state("bad", "✕ FOLDER NOT FOUND")
        else:
            self._set_state("idle")
        self.path_changed.emit(text)

    def get_path(self) -> str:
        return self.path_edit.text().strip()

    def set_path(self, path: str):
        self.path_edit.setText(path)

    # ── Drag and drop ──
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(Path(u.toLocalFile()).is_dir()
                                              for u in event.mimeData().urls()):
            event.acceptProposedAction()
            self._drag_active = True
            self.update()
            return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._drag_active = False
        self.update()

    def dropEvent(self, event):
        self._drag_active = False
        for url in event.mimeData().urls():
            if Path(url.toLocalFile()).is_dir():
                self.path_edit.setText(url.toLocalFile())
                break
        self.update()
