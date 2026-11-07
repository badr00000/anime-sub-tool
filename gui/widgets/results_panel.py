from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from gui.theme import Colors, add_glow


class ResultsPanel(QWidget):
    process_another_requested = Signal()
    open_folder_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("resultsPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        self.title = QLabel("MISSION COMPLETE")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle = QLabel("")
        self.subtitle.setProperty("role", "pageSubtitle")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        cards = QHBoxLayout()
        cards.setSpacing(14)
        self.total_card, self.total_value = self._make_card("TOTAL", Colors.text)
        self.success_card, self.success_value = self._make_card("DONE", Colors.blue_bright)
        self.failed_card, self.failed_value = self._make_card("FAILED", Colors.red)
        self.skipped_card, self.skipped_value = self._make_card("CANCELLED", Colors.text_muted)
        for card in (self.total_card, self.success_card, self.failed_card, self.skipped_card):
            cards.addWidget(card)

        buttons = QHBoxLayout()
        self.open_btn = QPushButton("OPEN OUTPUT FOLDER")
        self.open_btn.setFixedHeight(44)
        self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_btn.clicked.connect(self.open_folder_requested.emit)
        self.another_btn = QPushButton("NEW SEASON  ▸")
        self.another_btn.setObjectName("primaryButton")
        self.another_btn.setFixedHeight(44)
        self.another_btn.setMinimumWidth(200)
        self.another_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.another_btn.clicked.connect(self.process_another_requested.emit)
        add_glow(self.another_btn, Colors.blue, 26)
        buttons.addStretch()
        buttons.addWidget(self.open_btn)
        buttons.addSpacing(10)
        buttons.addWidget(self.another_btn)
        buttons.addStretch()

        # Keep a reference so the old API (time_lbl) still exists for callers
        self.time_lbl = self.subtitle

        layout.addStretch()
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        layout.addSpacing(14)
        layout.addLayout(cards)
        layout.addSpacing(18)
        layout.addLayout(buttons)
        layout.addStretch()
        self._style_title(Colors.blue_bright, Colors.blue)

    def _style_title(self, color: str, glow: str):
        self.title.setStyleSheet(f"font-size: 34px; font-weight: 900; letter-spacing: 6px;"
                                 f" color: {color}; background: transparent;")
        add_glow(self.title, glow, 30)

    def _make_card(self, title: str, color: str) -> tuple[QFrame, QLabel]:
        frame = QFrame(self)
        frame.setObjectName("card")
        frame.setStyleSheet(f"QFrame#card {{ border-top: 2px solid {color}; }}")
        frame.setMinimumSize(150, 120)

        f = QVBoxLayout(frame)
        f.setContentsMargins(16, 16, 16, 16)
        value = QLabel("0")
        value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value.setStyleSheet(f"font-size: 40px; font-weight: 900; color: {color}; background: transparent;")
        label = QLabel(title)
        label.setProperty("role", "fieldLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"color: {Colors.text_muted};")
        f.addWidget(value)
        f.addWidget(label)
        return frame, value

    def show_results(self, result):
        if not result:
            return
        self.total_value.setText(str(result.total))
        self.success_value.setText(str(result.successful))
        self.failed_value.setText(str(result.failed))
        self.skipped_value.setText(str(getattr(result, "cancelled", 0)))

        if result.failed > 0:
            self.title.setText("COMPLETED WITH ERRORS")
            reasons = [r.message for r in getattr(result, "results", [])
                       if getattr(r, "status", None) is not None and r.status.name == "FAILED" and r.message]
            shown = "\n".join(f"✕ {m}" for m in reasons[:3])
            more = f"\n…and {len(reasons) - 3} more" if len(reasons) > 3 else ""
            self.subtitle.setText(shown + more if shown else "Some episodes failed.")
            self.subtitle.setWordWrap(True)
            self._style_title(Colors.red_bright, Colors.red)
        else:
            self.title.setText("MISSION COMPLETE")
            self.subtitle.setText("Your episodes are ready in the output folder.")
            self._style_title(Colors.blue_bright, Colors.blue)
