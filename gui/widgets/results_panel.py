from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.models import ProcessingStatus
from gui.theme import Colors, add_glow

_MAX_REASONS = 3


class ResultsPanel(QWidget):
    process_another_requested = Signal()
    open_folder_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("resultsPanel")
        # "complete" | "errors" | "cancelled" | "dry_run" | "nothing"
        self.state = "complete"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        # Both labels can show text that comes from files (names, mkvmerge
        # messages), so they never interpret markup.
        self.title = QLabel("MISSION COMPLETE")
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle = QLabel("")
        self.subtitle.setTextFormat(Qt.TextFormat.PlainText)
        self.subtitle.setProperty("role", "pageSubtitle")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setWordWrap(True)

        cards = QHBoxLayout()
        cards.setSpacing(14)
        self.total_card, self.total_value = self._make_card("TOTAL", Colors.text)
        self.success_card, self.success_value, self.success_label = self._make_card(
            "DONE", Colors.blue_bright, with_label=True)
        self.skipped_card, self.skipped_value = self._make_card("SKIPPED", Colors.amber)
        self.failed_card, self.failed_value = self._make_card("FAILED", Colors.red)
        self.cancelled_card, self.cancelled_value = self._make_card("CANCELLED", Colors.text_muted)
        for card in (self.total_card, self.success_card, self.skipped_card,
                     self.failed_card, self.cancelled_card):
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

    def _make_card(self, title: str, color: str, with_label: bool = False):
        frame = QFrame(self)
        frame.setObjectName("card")
        frame.setStyleSheet(f"QFrame#card {{ border-top: 2px solid {color}; }}")
        frame.setMinimumSize(120, 120)

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
        return (frame, value, label) if with_label else (frame, value)

    @staticmethod
    def _reasons(result, status: ProcessingStatus, mark: str) -> list[str]:
        messages = [r.message for r in result.results if r.status == status and r.message]
        lines = [f"{mark} {m}" for m in messages[:_MAX_REASONS]]
        if len(messages) > _MAX_REASONS:
            lines.append(f"…and {len(messages) - _MAX_REASONS} more")
        return lines

    def show_results(self, result):
        if not result:
            return
        self.total_value.setText(str(result.total))
        self.success_value.setText(str(result.successful))
        self.skipped_value.setText(str(result.skipped))
        self.failed_value.setText(str(result.failed))
        self.cancelled_value.setText(str(result.cancelled))
        self.success_label.setText("WOULD DO" if result.dry_run else "DONE")

        details = (self._reasons(result, ProcessingStatus.FAILED, "✕")
                   + self._reasons(result, ProcessingStatus.SKIPPED, "–"))

        if result.cancelled > 0:
            self.state = "cancelled"
            title, color, glow = "CANCELLED", Colors.amber, Colors.amber
            if result.dry_run:
                lead = "The dry run was stopped before it finished."
            else:
                lead = (f"The batch was stopped: {result.successful} episode(s) finished, "
                        f"{result.cancelled} not processed.")
        elif result.failed > 0:
            self.state = "errors"
            title, color, glow = "COMPLETED WITH ERRORS", Colors.red_bright, Colors.red
            lead = "" if details else "Some episodes failed."
        elif result.dry_run:
            self.state = "dry_run"
            title, color, glow = "DRY RUN — NOTHING WRITTEN", Colors.amber, Colors.amber
            lead = (f"Simulation only: {result.successful} episode(s) would be processed. "
                    "No file was created or changed.")
        elif result.successful == 0:
            self.state = "nothing"
            title, color, glow = "NOTHING PROCESSED", Colors.amber, Colors.amber
            lead = "No episode was processed."
        else:
            self.state = "complete"
            title, color, glow = "MISSION COMPLETE", Colors.blue_bright, Colors.blue
            lead = "Your episodes are ready in the output folder."

        self.title.setText(title)
        self.subtitle.setText("\n".join(([lead] if lead else []) + details))
        self._style_title(color, glow)
