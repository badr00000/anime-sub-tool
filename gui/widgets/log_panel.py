import html
import time

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from core.constants import LOG_MAX_LINES
from gui.theme import Colors

LEVEL_STYLE = {
    "INFO": ("info", Colors.text_secondary),
    "SUCCESS": ("done", Colors.text),
    "WARNING": ("warn", Colors.warning),
    "ERROR": ("error", Colors.negative),
}


class LogPanel(QWidget):
    """The batch log: time, level, message."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("logPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        controls = QHBoxLayout()
        title = QLabel("Log")
        title.setProperty("role", "sectionLabel")
        self.autoscroll_cb = QCheckBox("Auto-scroll")
        self.autoscroll_cb.setChecked(True)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear)
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.clicked.connect(self.copy_all)
        for b in (self.clear_btn, self.copy_btn):
            b.setObjectName("ghostButton")
            b.setFixedHeight(32)

        controls.addWidget(title)
        controls.addStretch()
        controls.addWidget(self.autoscroll_cb)
        controls.addSpacing(8)
        controls.addWidget(self.clear_btn)
        controls.addWidget(self.copy_btn)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.document().setMaximumBlockCount(LOG_MAX_LINES)

        layout.addLayout(controls)
        layout.addWidget(self.text_edit)

    def append_log(self, message: str, level: str = "INFO"):
        tag, color = LEVEL_STYLE.get(level, LEVEL_STYLE["INFO"])
        stamp = time.strftime("%H:%M:%S")
        self.text_edit.append(
            f'<span style="color:{Colors.text_muted}">{stamp}</span>&nbsp;&nbsp;'
            f'<span style="color:{Colors.text_muted}">{tag.ljust(5).replace(" ", "&nbsp;")}</span>&nbsp;'
            f'<span style="color:{color}">{html.escape(message)}</span>'
        )
        if self.autoscroll_cb.isChecked():
            self.text_edit.moveCursor(QTextCursor.MoveOperation.End)

    def clear(self):
        self.text_edit.clear()

    def copy_all(self):
        self.text_edit.selectAll()
        self.text_edit.copy()
        self.text_edit.moveCursor(QTextCursor.MoveOperation.End)
