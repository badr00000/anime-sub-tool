from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QCheckBox
from PySide6.QtGui import QTextCursor, QColor
from PySide6.QtCore import Qt
try:
    from core.constants import LOG_MAX_LINES
except ImportError:
    LOG_MAX_LINES = 5000

class LogPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("logPanel")
        
        layout = QVBoxLayout(self)
        
        controls = QHBoxLayout()
        self.autoscroll_cb = QCheckBox("Auto-scroll")
        self.autoscroll_cb.setChecked(True)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear)
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.clicked.connect(self.copy_all)
        
        controls.addWidget(self.autoscroll_cb)
        controls.addStretch()
        controls.addWidget(self.clear_btn)
        controls.addWidget(self.copy_btn)
        
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.document().setMaximumBlockCount(LOG_MAX_LINES)
        
        layout.addLayout(controls)
        layout.addWidget(self.text_edit)
        
    def append_log(self, message: str, level: str = "INFO"):
        color_map = {
            "SUCCESS": "#10b981",
            "WARNING": "#f59e0b",
            "ERROR": "#ef4444",
            "INFO": "#d1d5db"
        }
        color = color_map.get(level, "#d1d5db")
        html = f'<span style="color: {color};">{message}</span>'
        self.text_edit.append(html)
        
        if self.autoscroll_cb.isChecked():
            self.text_edit.moveCursor(QTextCursor.MoveOperation.End)
            
    def clear(self):
        self.text_edit.clear()
        
    def copy_all(self):
        self.text_edit.selectAll()
        self.text_edit.copy()
        self.text_edit.moveCursor(QTextCursor.MoveOperation.End)
