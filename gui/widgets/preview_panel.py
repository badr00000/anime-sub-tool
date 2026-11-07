from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QLabel, QHeaderView
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from gui.theme import Colors

try:
    from core.models import ScanResult, MatchConfidence
except ImportError:
    ScanResult = None
    MatchConfidence = None


class PreviewPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("previewPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.summary_label = QLabel("0 files matched.")
        self.summary_label.setProperty("role", "fieldLabel")

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["EP", "EPISODE FILE", "SUBTITLE FILE", "MATCH", "STATUS"])
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

        unmatched_count = len(scan_result.unmatched_videos)
        self.summary_label.setText(
            f"// {len(matches)} EPISODES SCANNED"
            + (f"   ·   <span style='color:{Colors.red}'>{unmatched_count} WITHOUT SUBTITLE</span>" if unmatched_count else "")
        )

        for i, match in enumerate(matches):
            # Episode number
            ep_num = match.video.episode_num or "?"
            ep_item = QTableWidgetItem(str(ep_num))
            ep_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # Video filename
            vid_item = QTableWidgetItem(match.video.filename)
            vid_item.setToolTip(match.video.filename)

            # Subtitle filename
            sub_name = match.subtitle.filename if match.subtitle else "— No match —"
            sub_item = QTableWidgetItem(sub_name)
            sub_item.setToolTip(sub_name)
            if not match.subtitle:
                sub_item.setForeground(QColor(Colors.red))

            # Confidence score
            score = match.score
            conf_item = QTableWidgetItem(f"{score:.0f}%")
            conf_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if score >= 80:
                conf_item.setForeground(QColor(Colors.blue_bright))
            elif score >= 50:
                conf_item.setForeground(QColor(Colors.amber))
            else:
                conf_item.setForeground(QColor(Colors.red))

            # Status
            status_text = "READY" if match.is_matched else "NO SUB"
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if not match.is_matched:
                status_item.setForeground(QColor(Colors.red))
            else:
                status_item.setForeground(QColor(Colors.blue_bright))

            self.table.setItem(i, 0, ep_item)
            self.table.setItem(i, 1, vid_item)
            self.table.setItem(i, 2, sub_item)
            self.table.setItem(i, 3, conf_item)
            self.table.setItem(i, 4, status_item)
