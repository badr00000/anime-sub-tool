"""Folder Picker — a drop area with a path field and a browse button."""

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from core.matcher import list_media_files
from gui.icons import pixmap
from gui.theme import Colors


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" + ("" if n == 1 else "s")


class FolderPicker(QFrame):
    """Drop a folder anywhere on the zone, or type/browse a path.

    Public API (used by the main window): path_changed, get_path(), set_path().
    """

    path_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("folderPicker")
        self.setAcceptDrops(True)
        self.setMinimumHeight(240)
        self._drag_active = False
        self._state = "idle"  # idle | ok | bad

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 32, 48, 32)
        layout.setSpacing(8)
        layout.addStretch(1)

        self.icon = QLabel()
        self.icon.setPixmap(pixmap("folder", Colors.text_secondary, 28))
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setStyleSheet("background: transparent;")

        self.headline = QLabel("Drop a season folder here")
        self.headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.headline.setStyleSheet(f"font-size: 16px; font-weight: 500; color: {Colors.text};"
                                    " background: transparent;")

        hint = QLabel("Episodes (.mkv, .mp4) and their subtitles (.srt, .ass) in the same folder")
        hint.setProperty("role", "hint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Or paste a folder path")
        self.path_edit.setMinimumHeight(36)
        self.path_edit.setMaximumWidth(640)
        self.path_edit.textChanged.connect(self._on_text_changed)

        self.browse_btn = QPushButton("Browse")
        self.browse_btn.setFixedHeight(36)
        self.browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_btn.clicked.connect(self._browse)
        row.addStretch(1)
        row.addWidget(self.path_edit, 4)
        row.addWidget(self.browse_btn)
        row.addStretch(1)

        self.status_label = QLabel("")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.icon)
        layout.addSpacing(4)
        layout.addWidget(self.headline)
        layout.addWidget(hint)
        layout.addSpacing(16)
        layout.addLayout(row)
        layout.addWidget(self.status_label)
        layout.addStretch(1)

    # ── Painting: a surface with a soft dashed outline that lights up while dragging ──
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(QColor(Colors.raised if self._drag_active else Colors.surface))
        line = Colors.accent if self._drag_active else (
            Colors.negative if self._state == "bad" else Colors.hairline_strong)
        pen = QPen(QColor(line), 1)
        pen.setDashPattern([4, 4])
        p.setPen(pen)
        p.drawRoundedRect(r, 12, 12)
        p.end()

    def _set_state(self, state: str, message: str = ""):
        self._state = state
        self.status_label.setText(message)
        self.status_label.setProperty("role", {"ok": "fieldLabel", "bad": "bad"}.get(state, "hint"))
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
            self._set_state("ok", f"{_count(len(videos), 'episode')} · {_count(len(subs), 'subtitle file')}")
        elif text.strip():
            self._set_state("bad", "Folder not found")
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
