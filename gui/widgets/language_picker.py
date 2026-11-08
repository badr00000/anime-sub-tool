"""
Language dropdowns: users pick 'Japanese (jpn)' instead of having to know the code.

LanguageCombo       — one language   (value() -> 'jpn' or '')
MultiLanguageCombo  — tick several   (values() -> ['jpn', 'eng'])
"""

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QComboBox

from core.languages import LANGUAGES, UNDETERMINED, display, normalize


class LanguageCombo(QComboBox):
    """Single language. Optional first entry with an empty value ('none' / 'off')."""

    def __init__(self, empty_label: str | None = None, include_undetermined: bool = False,
                 parent=None):
        super().__init__(parent)
        self.setMaxVisibleItems(16)
        if empty_label:
            self.addItem(empty_label, "")
        if include_undetermined:
            self.addItem(display(UNDETERMINED[0]), UNDETERMINED[0])
        for code, _ in LANGUAGES:
            self.addItem(display(code), code)

    def value(self) -> str:
        return self.currentData() or ""

    def set_value(self, code: str):
        code = normalize(code)
        idx = self.findData(code)
        if idx < 0 and code:                 # a code we don't list: keep it, don't lose it
            self.addItem(code, code)
            idx = self.count() - 1
        self.setCurrentIndex(max(idx, 0))


class MultiLanguageCombo(QComboBox):
    """Checkable list that stays open while ticking; the field shows the picked names."""

    changed = Signal()

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setMaxVisibleItems(16)
        self._model = QStandardItemModel(self)
        for code, _ in LANGUAGES:
            self._model.appendRow(self._make_item(code))
        self.setModel(self._model)

        # An editable-but-read-only line edit is the simplest way to show free summary text
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setPlaceholderText(placeholder)
        self.lineEdit().installEventFilter(self)
        self.view().viewport().installEventFilter(self)
        self._model.dataChanged.connect(self._on_changed)
        # QComboBox writes the "current item" into the line edit on its own; put the summary back
        self.currentIndexChanged.connect(lambda _: self._refresh_text())
        self._refresh_text()

    @staticmethod
    def _make_item(code: str) -> QStandardItem:
        item = QStandardItem(display(code))
        item.setData(code, Qt.ItemDataRole.UserRole)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        item.setData(Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
        return item

    # Keep the popup open: toggle the clicked row instead of selecting it
    def eventFilter(self, obj, event):
        if obj is self.lineEdit() and event.type() == QEvent.Type.MouseButtonRelease:
            self.showPopup()
            return True
        if obj is self.view().viewport() and event.type() == QEvent.Type.MouseButtonRelease:
            index = self.view().indexAt(event.position().toPoint())
            item = self._model.itemFromIndex(index)
            if item is not None:
                checked = item.checkState() == Qt.CheckState.Checked
                item.setCheckState(Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked)
            return True
        return super().eventFilter(obj, event)

    def hidePopup(self):
        super().hidePopup()
        self._refresh_text()

    def _on_changed(self, *args):
        self._refresh_text()
        self.changed.emit()

    def _refresh_text(self):
        self.lineEdit().setText(", ".join(display(c) for c in self.values()))
        self.lineEdit().setCursorPosition(0)
        self.setToolTip("\n".join(display(c) for c in self.values()))

    def values(self) -> list[str]:
        out = []
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                out.append(item.data(Qt.ItemDataRole.UserRole))
        return out

    def set_values(self, codes: list[str]):
        wanted = [normalize(c) for c in codes if c and c.strip()]
        known = {self._model.item(r).data(Qt.ItemDataRole.UserRole) for r in range(self._model.rowCount())}
        for code in wanted:
            if code not in known:            # keep codes we don't list (e.g. from an old preset)
                self._model.appendRow(self._make_item(code))
                known.add(code)
        self._model.blockSignals(True)
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            state = Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in wanted \
                else Qt.CheckState.Unchecked
            item.setCheckState(state)
        self._model.blockSignals(False)
        self._refresh_text()
        self.changed.emit()
