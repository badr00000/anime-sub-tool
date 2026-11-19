from typing import Optional

from PySide6.QtWidgets import (
    QComboBox, QHeaderView, QLabel, QStyledItemDelegate, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)
from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor

from core.engine import ProcessingEngine
from core.languages import display as language_display, name_of
from core.models import EpisodeInfo, MatchConfidence
from core.subtitles import UNCERTAIN_HINT, is_uncertain
from gui.theme import Colors, plain_tooltip

_UNCERTAIN = (MatchConfidence.MEDIUM, MatchConfidence.LOW)

SUBTITLE_COLUMN = 2
NONE_LABEL = "— none —"
PICK_HINT = ("Double-click, F2 or Enter to pick another subtitle for this episode "
             "(or none). Choices made by hand are reset when the folder is rescanned with "
             "SCAN FOLDER; an automatic Watch-folder rescan keeps them.")


def _same_file(a: Optional[EpisodeInfo], b: Optional[EpisodeInfo]) -> bool:
    return a is not None and b is not None and a.filepath == b.filepath


class _SubtitleDelegate(QStyledItemDelegate):
    """Edits the SUBTITLE FILE cell with a dropdown of every scanned subtitle."""

    def __init__(self, panel: "PreviewPanel"):
        super().__init__(panel.table)
        self.panel = panel

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.setObjectName("subtitlePicker")
        combo.addItem(NONE_LABEL, -1)
        scan = self.panel.scan_result
        current = scan.matches[index.row()].subtitle if scan else None
        for i, sub in enumerate(scan.subtitle_files if scan else []):
            owner = self.panel.row_using(sub)
            label = sub.filename
            if owner is not None and owner != index.row():
                label += f"   (now on EP {scan.matches[owner].video.label})"
            combo.addItem(label, i)
            combo.setItemData(combo.count() - 1, plain_tooltip(sub.filename), Qt.ItemDataRole.ToolTipRole)
        combo.setCurrentIndex(0 if current is None else max(0, self._index_of(combo, current)))
        # Picking an entry (mouse or Enter) applies it at once
        combo.activated.connect(lambda _=None, c=combo: self._commit(c))
        if parent.isVisible():
            QTimer.singleShot(0, combo.showPopup)
        return combo

    def _index_of(self, combo: QComboBox, sub: EpisodeInfo) -> int:
        files = self.panel.scan_result.subtitle_files
        for row in range(combo.count()):
            data = combo.itemData(row)
            if isinstance(data, int) and data >= 0 and files[data].filepath == sub.filepath:
                return row
        return -1

    def _commit(self, combo: QComboBox):
        self.commitData.emit(combo)
        self.closeEditor.emit(combo, QStyledItemDelegate.EndEditHint.NoHint)

    def setEditorData(self, editor, index):
        pass    # chosen in createEditor; the cell text is not the value

    def setModelData(self, editor, model, index):
        data = editor.currentData()
        scan = self.panel.scan_result
        if scan is None or not isinstance(data, int):
            return
        sub = scan.subtitle_files[data] if data >= 0 else None
        current = scan.matches[index.row()].subtitle
        if (sub is None and current is None) or _same_file(sub, current):
            return
        self.panel.choose_subtitle(index.row(), sub)


class _EnterOpensPicker(QObject):
    """Enter / Return / Space on a row opens its subtitle picker (F2 works too)."""

    def __init__(self, panel: "PreviewPanel"):
        super().__init__(panel)
        self.panel = panel

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Type.KeyPress
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space)
                and self.panel.table.state() != QTableWidget.State.EditingState):
            row = self.panel.table.currentRow()
            if row >= 0:
                self.panel.open_picker(row)
                return True
        return False


class PreviewPanel(QWidget):
    # A one-line message for the status bar ("moved X from episode 3")
    status_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("previewPanel")
        self.scan_result = None
        self.subtitle_language = ""
        # Choices made by hand, by video path -> subtitle path (None = no subtitle).
        # Re-applied when the subtitle language changes; a new scan clears them.
        self._manual: dict = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Rich text on purpose (coloured counters). Only numbers are ever inserted
        # into it; anything taken from a file name must go through html.escape first.
        self.summary_label = QLabel("0 files matched.")
        self.summary_label.setTextFormat(Qt.TextFormat.RichText)
        self.summary_label.setProperty("role", "fieldLabel")

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["EP", "EPISODE FILE", "SUBTITLE FILE  ▾", "TITLE MATCH", "STATUS"])
        self.table.horizontalHeaderItem(SUBTITLE_COLUMN).setToolTip(plain_tooltip(PICK_HINT))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        # Only the subtitle cells are editable (their items carry ItemIsEditable)
        self.table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked
                                   | QTableWidget.EditTrigger.EditKeyPressed)
        self.table.setItemDelegateForColumn(SUBTITLE_COLUMN, _SubtitleDelegate(self))
        self.table.installEventFilter(_EnterOpensPicker(self))
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        # Keep both ends of long names visible: group tag on the left, episode number on the right
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)

        layout.addWidget(self.summary_label)
        layout.addWidget(self.table)

    # ─── pairing by hand ───

    def row_using(self, sub: EpisodeInfo) -> Optional[int]:
        """The row whose episode has this subtitle, or None."""
        for row, match in enumerate(self.scan_result.matches if self.scan_result else []):
            if _same_file(match.subtitle, sub):
                return row
        return None

    def open_picker(self, row: int):
        """Open the subtitle dropdown of a row (keyboard: Enter, Space or F2)."""
        index = self.table.model().index(row, SUBTITLE_COLUMN)
        self.table.setCurrentIndex(index)
        self.table.edit(index)

    def choose_subtitle(self, row: int, subtitle: Optional[EpisodeInfo]):
        """Pair episode `row` with `subtitle` (None = no subtitle). A subtitle another
        episode had is moved: that episode is left without a subtitle."""
        scan = self.scan_result
        if scan is None or not 0 <= row < len(scan.matches):
            return
        moved_from = self._apply(row, subtitle)
        self.refresh()
        episode = scan.matches[row].video.label
        if subtitle is None:
            message = f"Episode {episode}: no subtitle"
        else:
            message = f"Episode {episode}: {subtitle.filename}"
        if moved_from is not None:
            message += f" (moved from episode {scan.matches[moved_from].video.label}, which now has none)"
        self.status_message.emit(message)

    def _apply(self, row: int, subtitle: Optional[EpisodeInfo]) -> Optional[int]:
        scan = self.scan_result
        moved_from = ProcessingEngine.set_manual_subtitle(scan, row, subtitle, self.subtitle_language)
        self._manual[scan.matches[row].video.filepath] = subtitle.filepath if subtitle else None
        if moved_from is not None:
            # Not a choice of its own: re-applying the pick above empties it again
            self._manual.pop(scan.matches[moved_from].video.filepath, None)
        return moved_from

    def set_subtitle_language(self, language: str):
        """Match again for another subtitle language, keeping the choices made by hand."""
        if self.scan_result is None or language == self.subtitle_language:
            return
        self.subtitle_language = language
        ProcessingEngine.rematch(self.scan_result, language)
        manual, self._manual = self._manual, {}
        rows = {m.video.filepath: i for i, m in enumerate(self.scan_result.matches)}
        subs = {s.filepath: s for s in self.scan_result.subtitle_files}
        for video_path, sub_path in manual.items():
            if video_path in rows:
                self._apply(rows[video_path], subs.get(sub_path) if sub_path else None)
        self.refresh()

    # ─── table ───

    def populate(self, scan_result, subtitle_language: Optional[str] = None,
                 keep_manual: bool = False) -> tuple[int, int]:
        """Show a ScanResult. A new scan clears the choices made by hand, unless
        keep_manual (an automatic Watch-folder rescan): then every choice whose
        episode and subtitle files are still in the new scan is applied again.
        Returns (choices kept, choices dropped)."""
        if not scan_result:
            return 0, 0
        manual = {}
        if scan_result is not self.scan_result:
            manual, self._manual = (self._manual if keep_manual else {}), {}
        self.scan_result = scan_result
        if subtitle_language is not None:
            self.subtitle_language = subtitle_language
        kept = dropped = 0
        if manual:
            rows = {m.video.filepath: i for i, m in enumerate(scan_result.matches)}
            subs = {s.filepath: s for s in scan_result.subtitle_files}
            for video_path, sub_path in manual.items():
                if video_path in rows and (sub_path is None or sub_path in subs):
                    self._apply(rows[video_path], subs[sub_path] if sub_path else None)
                    kept += 1
                else:
                    dropped += 1
        self.refresh()
        return kept, dropped

    def _item(self, row: int, column: int) -> QTableWidgetItem:
        item = self.table.item(row, column)
        if item is None:
            item = QTableWidgetItem()
            self.table.setItem(row, column, item)
        return item

    def refresh(self):
        """Redraw the table and counters from the current pairs. Existing items are
        updated in place (this also runs while a cell editor commits)."""
        scan_result = self.scan_result
        if scan_result is None:
            return
        matches = scan_result.matches
        self.table.setRowCount(len(matches))

        unmatched_count = sum(1 for m in matches if not m.is_matched)
        uncertain_count = sum(1 for m in matches if m.is_matched and (
            m.confidence in _UNCERTAIN or m.language_warning))
        manual_count = sum(1 for m in matches if m.is_manual)
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
        if manual_count:
            summary += f"   ·   <span style='color:{Colors.blue_bright}'>{manual_count} PAIRED BY HAND</span>"
        if unused_subs:
            summary += f"   ·   {unused_subs} SUBTITLE(S) UNUSED"
        self.summary_label.setText(summary)

        read_only = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        for i, match in enumerate(matches):
            # Episode number
            ep_item = self._item(i, 0)
            ep_item.setText(str(match.video.label))
            ep_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            ep_item.setFlags(read_only)

            # Video filename
            vid_item = self._item(i, 1)
            vid_item.setText(match.video.filename)
            vid_item.setToolTip(plain_tooltip(match.video.filename))
            vid_item.setFlags(read_only)

            # Subtitle filename (the tooltip also tells the detected encoding and language)
            if match.subtitle:
                sub_name = match.subtitle.filename
            elif match.is_manual:
                sub_name = "— none (chosen by hand) —"
            elif match.moved_to:
                sub_name = f"— none (moved to EP {match.moved_to}) —"
            else:
                sub_name = "— No match —"
            sub_item = self._item(i, SUBTITLE_COLUMN)
            sub_item.setFlags(read_only | Qt.ItemFlag.ItemIsEditable)
            sub_text = sub_name
            sub_tip = sub_name
            if match.subtitle and match.subtitle.encoding:
                sub_tip += f"\nEncoding: {match.subtitle.encoding}"
            if match.subtitle:
                tag = match.subtitle_language
                sub_tip += ("\nLanguage in the name: " + language_display(tag)) if tag else \
                    "\nLanguage in the name: none stated"
            encoding_uncertain = bool(match.subtitle and is_uncertain(match.subtitle.encoding))
            color = Colors.text
            if encoding_uncertain:
                sub_text = "⚠ " + sub_name
                color = Colors.amber
                sub_tip += f"\n⚠ {UNCERTAIN_HINT}"
            if not match.subtitle:
                color = Colors.red
            if match.is_manual:
                sub_tip += "\nChosen by hand."
            sub_tip += "\n\n" + PICK_HINT
            sub_item.setText(sub_text + "  ▾")
            sub_item.setForeground(QColor(color))
            sub_item.setToolTip(plain_tooltip(sub_tip))

            # Title similarity
            score = match.score
            conf_item = self._item(i, 3)
            conf_item.setFlags(read_only)
            conf_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if match.is_manual and match.is_matched:
                conf_item.setText("MANUAL")
                conf_item.setForeground(QColor(Colors.blue_bright))
            else:
                conf_item.setText(f"{score:.0f}%" if match.is_matched else "—")
                if score >= 80:
                    conf_item.setForeground(QColor(Colors.blue_bright))
                elif score >= 50:
                    conf_item.setForeground(QColor(Colors.amber))
                else:
                    conf_item.setForeground(QColor(Colors.red))

            # Status: matched by episode number; flagged when the titles disagree
            if not match.is_matched:
                status_text, status_color = "NO SUB", Colors.red
                if match.is_manual:
                    status_tip = ("You chose no subtitle for this episode. It is skipped unless "
                                  "'Also process episodes that have no subtitle' is ticked.")
                elif match.moved_to:
                    status_tip = (f"Its subtitle was moved to episode {match.moved_to}. The episode "
                                  "is skipped unless 'Also process episodes that have no "
                                  "subtitle' is ticked.")
                else:
                    status_tip = ("No subtitle with this episode number. The episode is skipped "
                                  "unless 'Also process episodes that have no subtitle' is ticked.")
            elif match.language_warning:
                status_text, status_color = "⚠ CHECK", Colors.amber
                status_tip = (f"Check: {match.language_warning}. "
                              f"Pick another subtitle, or change the subtitle LANGUAGE option "
                              f"(now {name_of(self.subtitle_language)}) if the name is right.")
            elif match.is_manual:
                status_text, status_color = "READY", Colors.blue_bright
                status_tip = "Subtitle chosen by hand."
            elif match.confidence in _UNCERTAIN:
                status_text = "⚠ CHECK"
                status_color = Colors.amber if match.confidence == MatchConfidence.MEDIUM else Colors.red
                if match.note:
                    status_tip = f"Check: {match.note}."
                else:
                    status_tip = ("Matched by episode number, but the two file names carry "
                                  "different titles. Normal when the subtitle uses another "
                                  "spelling or a translated title; make sure it is the same show.")
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
            status_item = self._item(i, 4)
            status_item.setFlags(read_only)
            status_item.setText(status_text)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setForeground(QColor(status_color))
            status_item.setToolTip(plain_tooltip(status_tip))
            conf_item.setToolTip(plain_tooltip(status_tip))
