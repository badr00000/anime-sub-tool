import html
import time

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from gui.theme import Colors

try:
    from core.constants import LOG_MAX_LINES
except ImportError:
    LOG_MAX_LINES = 5000

LEVEL_STYLE = {
    "INFO": ("INF", Colors.text_secondary),
    "SUCCESS": ("OK ", Colors.blue_bright),
    "WARNING": ("WRN", Colors.amber),
    "ERROR": ("ERR", Colors.red),
}


class LogPanel(QWidget):
    """Terminal-style log: time, level tag, message."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("logPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        controls = QHBoxLayout()
        title = QLabel("// LOG")
        title.setProperty("role", "fieldLabel")
        self.autoscroll_cb = QCheckBox("Auto-scroll")
        self.autoscroll_cb.setChecked(True)
        self.clear_btn = QPushButton("CLEAR")
        self.clear_btn.clicked.connect(self.clear)
        self.copy_btn = QPushButton("COPY")
        self.copy_btn.clicked.connect(self.copy_all)
        for b in (self.clear_btn, self.copy_btn):
            b.setFixedHeight(28)
            b.setStyleSheet("padding: 2px 12px; font-size: 11px;")

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
            f'<span style="color:{color}; font-weight:700">[{tag}]</span>&nbsp;&nbsp;'
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
