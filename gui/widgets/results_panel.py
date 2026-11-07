from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtCore import Signal, Qt


class ResultsPanel(QWidget):
    process_another_requested = Signal()
    open_folder_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("resultsPanel")

        layout = QVBoxLayout(self)
        layout.setSpacing(20)

        # Title
        self.title = QLabel("✅ Processing Complete")
        self.title.setStyleSheet("font-size: 26px; color: #10b981; font-weight: bold;")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Summary cards
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(12)

        self.total_card, self.total_value = self._make_card("Total", "0", "#6366f1")
        self.success_card, self.success_value = self._make_card("Succeeded", "0", "#10b981")
        self.failed_card, self.failed_value = self._make_card("Failed", "0", "#ef4444")
        self.skipped_card, self.skipped_value = self._make_card("Skipped", "0", "#9ca3af")

        cards_layout.addWidget(self.total_card)
        cards_layout.addWidget(self.success_card)
        cards_layout.addWidget(self.failed_card)
        cards_layout.addWidget(self.skipped_card)

        # Time stats
        self.time_lbl = QLabel("")
        self.time_lbl.setStyleSheet("color: #9ca3af; font-size: 14px;")
        self.time_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Buttons
        btn_layout = QHBoxLayout()
        self.open_btn = QPushButton("📂  Open Output Folder")
        self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_btn.clicked.connect(self.open_folder_requested.emit)
        self.another_btn = QPushButton("🔄  Process Another Folder")
        self.another_btn.setObjectName("primaryButton")
        self.another_btn.setFixedHeight(42)
        self.another_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.another_btn.clicked.connect(self.process_another_requested.emit)

        btn_layout.addWidget(self.open_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.another_btn)

        layout.addStretch()
        layout.addWidget(self.title)
        layout.addSpacing(10)
        layout.addLayout(cards_layout)
        layout.addWidget(self.time_lbl)
        layout.addStretch()
        layout.addLayout(btn_layout)

    def _make_card(self, title: str, value: str, color: str) -> tuple[QFrame, QLabel]:
        """Create a summary card widget. Returns (frame, value_label)."""
        frame = QFrame(self)  # Parent to self to prevent GC
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: #1a1f2e;
                border: 1px solid #374151;
                border-radius: 12px;
                padding: 16px;
            }}
        """)
        frame.setMinimumWidth(140)

        flayout = QVBoxLayout(frame)
        flayout.setSpacing(4)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #9ca3af; font-size: 12px; background: transparent;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        value_lbl = QLabel(value)
        value_lbl.setStyleSheet(f"font-size: 28px; font-weight: bold; color: {color}; background: transparent;")
        value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        flayout.addWidget(title_lbl)
        flayout.addWidget(value_lbl)

        return frame, value_lbl

    def show_results(self, result):
        """Populate results from a BatchResult."""
        if not result:
            return

        self.total_value.setText(str(result.total))
        self.success_value.setText(str(result.successful))
        self.failed_value.setText(str(result.failed))
        self.skipped_value.setText(str(getattr(result, 'skipped', 0)))

        # Update title color based on results
        if result.failed > 0:
            self.title.setText("⚠️ Processing Complete (with errors)")
            self.title.setStyleSheet("font-size: 26px; color: #f59e0b; font-weight: bold;")
        else:
            self.title.setText("✅ Processing Complete!")
            self.title.setStyleSheet("font-size: 26px; color: #10b981; font-weight: bold;")
