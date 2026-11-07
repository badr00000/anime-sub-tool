"""Series Name Input Widget — Text input with auto-detect button."""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton, QLabel, QVBoxLayout
from PySide6.QtCore import Signal, Qt


class SeriesInput(QWidget):
    """Series name input with auto-detect capability."""

    auto_detect_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("seriesInput")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Label
        label = QLabel("SERIES NAME  (OPTIONAL)")
        label.setProperty("role", "fieldLabel")

        # Input row
        row = QHBoxLayout()
        row.setSpacing(8)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Leave empty to auto-detect from filenames...")
        self.name_edit.setMinimumHeight(40)

        self.auto_btn = QPushButton("AUTO")
        self.auto_btn.setFixedHeight(40)
        self.auto_btn.setFixedWidth(110)
        self.auto_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.auto_btn.setToolTip("Detect series name from filenames automatically")
        self.auto_btn.clicked.connect(self.auto_detect_requested.emit)

        row.addWidget(self.name_edit, 1)
        row.addWidget(self.auto_btn)

        layout.addWidget(label)
        layout.addLayout(row)

    def get_series_name(self) -> str:
        return self.name_edit.text().strip()

    def set_series_name(self, name: str):
        self.name_edit.setText(name)
