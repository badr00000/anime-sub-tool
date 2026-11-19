from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QLabel, QHeaderView
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from core.models import MatchConfidence
from core.subtitles import UNCERTAIN_HINT, is_uncertain
from gui.theme import Colors, plain_tooltip

_UNCERTAIN = (MatchConfidence.MEDIUM, MatchConfidence.LOW)


class PreviewPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("previewPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Rich text on purpose (coloured counters). Only numbers are ever inserted
        # into it; anything taken from a file name must go through html.escape first.
        self.summary_label = QLabel("0 files matched.")
        self.summary_label.setTextFormat(Qt.TextFormat.RichText)
        self.summary_label.setProperty("role", "fieldLabel")

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["EP", "EPISODE FILE", "SUBTITLE FILE", "TITLE MATCH", "STATUS"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        # Keep both ends of long names visible: group tag on the left, episode number on the right
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)

        layout.addWidget(self.summary_label)
        layout.addWidget(self.table)

    def populate(self, scan_result):
        """Populate table from a ScanResult."""
        if not scan_result:
            return

        matches = scan_result.matches
        self.table.setRowCount(len(matches))

        unmatched_count = sum(1 for m in matches if not m.is_matched)
        uncertain_count = sum(1 for m in matches if m.is_matched and m.confidence in _UNCERTAIN)
        unused_subs = len(scan_result.unmatched_subtitles)
        encoding_count = sum(1 for m in matches if m.subtitle and is_uncertain(m.subtitle.encoding))
        summary = f"// {len(matches)} EPISODES SCANNED"
        if unmatched_count:
            summary += f"   ·   <span style='color:{Colors.red}'>{unmatched_count} WITHOUT SUBTITLE</span>"
        if uncertain_count:
            summary += f"   ·   <span style='color:{Colors.amber}'>{uncertain_count} TO CHECK</span>"
        if encoding_count:
            summary += (f"   ·   <span style='color:{Colors.amber}'>⚠ {encoding_count} "
                        "ENCODING UNCERTAIN</span>")
        if unused_subs:
            summary += f"   ·   {unused_subs} SUBTITLE(S) UNUSED"
        self.summary_label.setText(summary)

        for i, match in enumerate(matches):
            # Episode number
            ep_num = match.video.label
            ep_item = QTableWidgetItem(str(ep_num))
            ep_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # Video filename
            vid_item = QTableWidgetItem(match.video.filename)
            vid_item.setToolTip(plain_tooltip(match.video.filename))

            # Subtitle filename (the tooltip also tells the detected encoding)
            sub_name = match.subtitle.filename if match.subtitle else "— No match —"
            sub_item = QTableWidgetItem(sub_name)
            sub_tip = sub_name
            if match.subtitle and match.subtitle.encoding:
                sub_tip += f"\nEncoding: {match.subtitle.encoding}"
            encoding_uncertain = bool(match.subtitle and is_uncertain(match.subtitle.encoding))
            if encoding_uncertain:
                sub_item.setText("⚠ " + sub_name)
                sub_item.setForeground(QColor(Colors.amber))
                sub_tip += f"\n⚠ {UNCERTAIN_HINT}"
            sub_item.setToolTip(plain_tooltip(sub_tip))
            if not match.subtitle:
                sub_item.setForeground(QColor(Colors.red))

            # Title similarity
            score = match.score
            conf_item = QTableWidgetItem(f"{score:.0f}%" if match.is_matched else "—")
            conf_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if score >= 80:
                conf_item.setForeground(QColor(Colors.blue_bright))
            elif score >= 50:
                conf_item.setForeground(QColor(Colors.amber))
            else:
                conf_item.setForeground(QColor(Colors.red))

            # Status: matched by episode number; flagged when the titles disagree
            if not match.is_matched:
                status_text, status_color = "NO SUB", Colors.red
                status_tip = ("No subtitle with this episode number. The episode is skipped "
                              "unless 'Also process episodes that have no subtitle' is ticked.")
            elif match.confidence in _UNCERTAIN:
                status_text = "⚠ CHECK"
                status_color = Colors.amber if match.confidence == MatchConfidence.MEDIUM else Colors.red
                status_tip = ("Matched by episode number, but the two file names carry different "
                              "titles. Normal when the subtitle uses another spelling or a "
                              "translated title; make sure it is the same show.")
            else:
                status_text, status_color = "READY", Colors.blue_bright
                status_tip = "Episode number and title agree."
            if encoding_uncertain:
                if status_text == "READY":
                    status_text, status_color = "⚠ ENCODING", Colors.amber
                    status_tip = ""
                status_tip = (status_tip + "\n\n" if status_tip else "") + (
                    f"Subtitle {UNCERTAIN_HINT}: auto-detect could not tell which code page "
                    "it uses, so it would be merged unconverted.")
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setForeground(QColor(status_color))
            status_item.setToolTip(plain_tooltip(status_tip))
            conf_item.setToolTip(plain_tooltip(status_tip))

            self.table.setItem(i, 0, ep_item)
            self.table.setItem(i, 1, vid_item)
            self.table.setItem(i, 2, sub_item)
            self.table.setItem(i, 3, conf_item)
            self.table.setItem(i, 4, status_item)
