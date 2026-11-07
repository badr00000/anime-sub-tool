"""Progress Panel — Real-time progress display during processing."""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton
from PySide6.QtCore import Signal, Qt


class ProgressPanel(QWidget):
    """Displays processing progress with ETA and speed indicators."""

    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("progressPanel")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Current file label
        self.file_label = QLabel("Preparing...")
        self.file_label.setStyleSheet("""
            font-size: 16px;
            font-weight: 700;
            color: #f1f5f9;
        """)

        # Progress percentage
        self.percent_label = QLabel("0%")
        self.percent_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.percent_label.setStyleSheet("""
            font-size: 36px;
            font-weight: 800;
            color: #a5b4fc;
        """)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setTextVisible(False)

        # Stats row
        stats_layout = QHBoxLayout()
        self.speed_label = QLabel("Speed: --")
        self.speed_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
        self.eta_label = QLabel("ETA: --")
        self.eta_label.setStyleSheet("color: #94a3b8; font-size: 12px;")

        stats_layout.addWidget(self.speed_label)
        stats_layout.addStretch()
        stats_layout.addWidget(self.eta_label)

        # Cancel button
        self.cancel_btn = QPushButton("Cancel Processing")
        self.cancel_btn.setObjectName("dangerButton")
        self.cancel_btn.setFixedHeight(36)
        self.cancel_btn.setFixedWidth(180)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)

        layout.addWidget(self.file_label)
        layout.addWidget(self.percent_label)
        layout.addWidget(self.progress_bar)
        layout.addLayout(stats_layout)
        layout.addSpacing(4)
        layout.addWidget(self.cancel_btn, 0, Qt.AlignmentFlag.AlignCenter)

    def update_progress(self, current: int, total: int, file_name: str = "",
                        speed: str = "", eta: str = ""):
        """Update progress display."""
        self.file_label.setText(f"Processing: {file_name}" if file_name else "Processing...")

        if total > 0:
            pct = min(int((current / total) * 100), 100)
            self.progress_bar.setValue(pct)
            self.percent_label.setText(f"{pct}%")

        if speed:
            self.speed_label.setText(f"Speed: {speed}")
        if eta:
            self.eta_label.setText(f"ETA: {eta}")

    def reset(self):
        """Reset to initial state."""
        self.progress_bar.setValue(0)
        self.percent_label.setText("0%")
        self.file_label.setText("Preparing...")
        self.speed_label.setText("Speed: --")
        self.eta_label.setText("ETA: --")
