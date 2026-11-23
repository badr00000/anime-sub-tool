"""Results page: what happened to each episode of the season, at a glance."""

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from core.models import ProcessingStatus
from gui.theme import Colors, plain_tooltip, page_header
from gui.widgets.preview_panel import episode_chip_text

_MAX_REASONS = 3

# How each outcome looks in the season strip: (fill, outline, text)
_CELL = {
    "done": (Colors.accent_soft, Colors.accent, Colors.text),
    "skipped": (Colors.surface, Colors.hairline_strong, Colors.text_muted),
    "failed": (Colors.negative_soft, Colors.negative, Colors.text),
    "cancelled": (Colors.bg, Colors.hairline_strong, Colors.text_muted),
}
_STATUS_KIND = {
    ProcessingStatus.COMPLETED: "done",
    ProcessingStatus.COMPLETED_WITH_WARNINGS: "done",
    ProcessingStatus.SKIPPED: "skipped",
    ProcessingStatus.FAILED: "failed",
    ProcessingStatus.CANCELLED: "cancelled",
}
_KIND_WORD = {"done": "merged", "skipped": "skipped", "failed": "failed", "cancelled": "cancelled"}


class SeasonStrip(QWidget):
    """One cell per episode, in season order, filled by its outcome."""

    CELL_W, CELL_H, GAP = 64, 40, 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cells: list[tuple[str, str, str]] = []     # (chip text, kind, file name)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    def set_cells(self, cells):
        self.cells = list(cells)
        self._relayout()
        self.update()

    def _per_row(self) -> int:
        return max(1, (self.width() + self.GAP) // (self.CELL_W + self.GAP))

    def _relayout(self):
        rows = max(1, -(-len(self.cells) // self._per_row())) if self.cells else 1
        self.setFixedHeight(rows * self.CELL_H + (rows - 1) * self.GAP)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def _rect(self, i: int) -> QRectF:
        per_row = self._per_row()
        row, col = divmod(i, per_row)
        return QRectF(col * (self.CELL_W + self.GAP) + 0.5, row * (self.CELL_H + self.GAP) + 0.5,
                      self.CELL_W - 1, self.CELL_H - 1)

    def mouseMoveEvent(self, event):
        for i, (chip, kind, name) in enumerate(self.cells):
            if self._rect(i).contains(event.position()):
                self.setToolTip(plain_tooltip(f"{name}\n{_KIND_WORD[kind].capitalize()}"))
                return
        self.setToolTip("")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPixelSize(11)
        p.setFont(font)
        for i, (chip, kind, _) in enumerate(self.cells):
            fill, line, text = _CELL[kind]
            r = self._rect(i)
            pen = QPen(QColor(line), 1)
            if kind == "cancelled":
                pen.setDashPattern([3, 3])
            p.setPen(pen)
            p.setBrush(QColor(fill))
            p.drawRoundedRect(r, 8, 8)
            p.setPen(QColor(text))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, chip)
        p.end()


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
        layout.setSpacing(24)

        header = page_header("Season merged", "")
        self.title, self.subtitle = header.findChildren(QLabel)
        # Both labels can show text that comes from files (names, mkvmerge
        # messages), so they never interpret markup.
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.subtitle.setTextFormat(Qt.TextFormat.PlainText)
        self.subtitle.setWordWrap(True)

        card = QFrame()
        card.setObjectName("card")
        inner = QVBoxLayout(card)
        inner.setContentsMargins(24, 20, 24, 24)
        inner.setSpacing(20)

        stats = QHBoxLayout()
        stats.setSpacing(40)
        self.total_value = self._stat(stats, "Episodes")
        self.success_value, self.success_label = self._stat(stats, "Merged", with_label=True)
        self.skipped_value = self._stat(stats, "Skipped")
        self.failed_value = self._stat(stats, "Failed")
        self.cancelled_value = self._stat(stats, "Cancelled")
        stats.addStretch()

        strip_label = QLabel("Each episode of the season")
        strip_label.setProperty("role", "sectionLabel")
        self.strip = SeasonStrip()

        inner.addLayout(stats)
        inner.addWidget(strip_label)
        inner.addWidget(self.strip)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.another_btn = QPushButton("Merge another season")
        self.another_btn.setObjectName("primaryButton")
        self.another_btn.setFixedHeight(40)
        self.another_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.another_btn.clicked.connect(self.process_another_requested.emit)
        self.open_btn = QPushButton("Open output folder")
        self.open_btn.setFixedHeight(40)
        self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_btn.clicked.connect(self.open_folder_requested.emit)
        buttons.addWidget(self.another_btn)
        buttons.addWidget(self.open_btn)
        buttons.addStretch()

        layout.addWidget(header)
        layout.addWidget(card)
        layout.addLayout(buttons)
        layout.addStretch()

    def _stat(self, row: QHBoxLayout, label: str, with_label: bool = False):
        box = QVBoxLayout()
        box.setSpacing(4)
        value = QLabel("0")
        value.setStyleSheet(f"font-family: {Colors.font_mono}; font-size: 28px; font-weight: 500;"
                            f" color: {Colors.text}; background: transparent;")
        caption = QLabel(label)
        caption.setProperty("role", "fieldLabel")
        box.addWidget(value)
        box.addWidget(caption)
        row.addLayout(box)
        return (value, caption) if with_label else value

    @staticmethod
    def _reasons(result, status: ProcessingStatus, word: str) -> list[str]:
        messages = [r.message for r in result.results if r.status == status and r.message]
        lines = [f"{word}: {m}" for m in messages[:_MAX_REASONS]]
        if len(messages) > _MAX_REASONS:
            lines.append(f"…and {len(messages) - _MAX_REASONS} more")
        return lines

    @staticmethod
    def _cells(result, matches):
        """Strip cells in season order (the scan's order); results carry their video name."""
        by_name = {r.video_name: _STATUS_KIND.get(r.status, "cancelled")
                   for r in result.results if r.video_name}
        if matches:
            return [(episode_chip_text(m.video.label), by_name.get(m.video.filename, "cancelled"),
                     m.video.filename) for m in matches]
        return [(str(i + 1), _STATUS_KIND.get(r.status, "cancelled"), r.video_name or "")
                for i, r in enumerate(result.results)]

    def show_results(self, result, matches=None):
        if not result:
            return
        self.total_value.setText(str(result.total))
        self.success_value.setText(str(result.successful))
        self.skipped_value.setText(str(result.skipped))
        self.failed_value.setText(str(result.failed))
        self.cancelled_value.setText(str(result.cancelled))
        self.success_label.setText("Would merge" if result.dry_run else "Merged")
        self.failed_value.setStyleSheet(self.total_value.styleSheet().replace(
            Colors.text, Colors.negative if result.failed else Colors.text))
        self.strip.set_cells(self._cells(result, matches))

        details = (self._reasons(result, ProcessingStatus.FAILED, "Failed")
                   + self._reasons(result, ProcessingStatus.SKIPPED, "Skipped"))

        if result.cancelled > 0:
            self.state = "cancelled"
            title = "Cancelled"
            if result.dry_run:
                lead = "The dry run was stopped before it finished."
            else:
                lead = (f"The batch was stopped: {result.successful} episode(s) finished, "
                        f"{result.cancelled} not processed.")
        elif result.failed > 0:
            self.state = "errors"
            title = "Merged with errors"
            lead = "" if details else "Some episodes failed."
        elif result.dry_run:
            self.state = "dry_run"
            title = "Dry run, nothing written"
            lead = (f"Simulation only: {result.successful} episode(s) would be processed. "
                    "No file was created or changed.")
        elif result.successful == 0:
            self.state = "nothing"
            title = "Nothing processed"
            lead = "No episode was processed."
        else:
            self.state = "complete"
            title = "Season merged"
            lead = "The new files are ready in the output folder."

        self.title.setText(title)
        self.subtitle.setText("\n".join(([lead] if lead else []) + details))
