"""
Language dropdowns: users pick 'Japanese (jpn)' instead of having to know the code,
and can type to search (English name, code, or Arabic name such as 'ياباني').

LanguageCombo       — one language   (value() -> 'jpn' or '')
MultiLanguageCombo  — tick several   (values() -> ['jpn', 'eng'])
"""

from PySide6.QtCore import QEvent, QModelIndex, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox, QFrame, QLabel, QLineEdit, QListView, QVBoxLayout,
)

from core.languages import LANGUAGES, UNDETERMINED, display, normalize, search_text
from gui.theme import plain_tooltip

CODE_ROLE = Qt.ItemDataRole.UserRole
SEARCH_ROLE = Qt.ItemDataRole.UserRole + 1


def _fold(text: str) -> str:
    """Lower-case and fold Arabic letter variants so 'يابانى' finds 'ياباني'."""
    text = (text or "").lower()
    for a, b in (("ى", "ي"), ("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ـ", "")):
        text = text.replace(a, b)
    return text


class _SearchProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._words: list[str] = []

    def set_query(self, text: str):
        self._words = _fold(text).split()
        self.invalidateFilter()

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:
        if not self._words:
            return True
        hay = _fold(self.sourceModel().index(row, 0, parent).data(SEARCH_ROLE) or "")
        return all(w in hay for w in self._words)


class _SearchPopup(QFrame):
    """Search box + filtered list, shown under the combo instead of Qt's own popup."""

    def __init__(self, combo: QComboBox, multi: bool):
        super().__init__(combo, Qt.WindowType.Popup)
        self.setObjectName("langPopup")
        self._combo = combo
        self._multi = multi

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search…  Japanese · jpn · ياباني")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._on_query)
        self.search.installEventFilter(self)

        self.proxy = _SearchProxy(self)
        self.proxy.setSourceModel(combo.model())

        self.list = QListView()
        self.list.setModel(self.proxy)
        self.list.setUniformItemSizes(True)
        self.list.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self.list.clicked.connect(self._activate)
        self.list.activated.connect(self._activate)
        if multi:
            # click anywhere on the row toggles it (handled in _activate), not only the box
            self.list.viewport().installEventFilter(self)

        self.empty = QLabel("No language matches")
        self.empty.setProperty("role", "hint")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.hide()

        lay.addWidget(self.search)
        lay.addWidget(self.list, 1)
        lay.addWidget(self.empty)

    def open(self):
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.proxy.set_query("")
        self.empty.hide()
        width = max(self._combo.width(), 260)
        self.resize(width, 360)
        pos = self._combo.mapToGlobal(self._combo.rect().bottomLeft())
        screen = self._combo.screen().availableGeometry()
        if pos.y() + self.height() > screen.bottom():       # not enough room below: open above
            pos = self._combo.mapToGlobal(self._combo.rect().topLeft())
            pos.setY(pos.y() - self.height())
        self.move(pos)
        if not self._multi and self._combo.currentIndex() >= 0:
            idx = self.proxy.mapFromSource(self._combo.model().index(self._combo.currentIndex(), 0))
            self.list.setCurrentIndex(idx)
            self.list.scrollTo(idx, QListView.ScrollHint.PositionAtCenter)
        else:
            self.list.scrollToTop()
        self.show()
        self.search.setFocus()

    def _on_query(self, text: str):
        self.proxy.set_query(text)
        has_rows = self.proxy.rowCount() > 0
        self.empty.setVisible(not has_rows)
        if has_rows:
            self.list.setCurrentIndex(self.proxy.index(0, 0))

    def _activate(self, proxy_index):
        if not proxy_index.isValid():
            return
        src = self.proxy.mapToSource(proxy_index)
        if self._multi:
            item = self._combo.model().itemFromIndex(src)
            checked = item.checkState() == Qt.CheckState.Checked
            item.setCheckState(Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked)
        else:
            self._combo.setCurrentIndex(src.row())
            self.hide()

    def eventFilter(self, obj, event):
        if obj is self.search and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                row = self.list.currentIndex().row() + (1 if key == Qt.Key.Key_Down else -1)
                row = max(0, min(row, self.proxy.rowCount() - 1))
                self.list.setCurrentIndex(self.proxy.index(row, 0))
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._activate(self.list.currentIndex())
                return True
        if self._multi and obj is self.list.viewport() and event.type() == QEvent.Type.MouseButtonRelease:
            self._activate(self.list.indexAt(event.position().toPoint()))
            return True
        if self._multi and obj is self.list.viewport() and event.type() == QEvent.Type.MouseButtonPress:
            return True  # avoid the default "click on checkbox" toggling it a second time
        return super().eventFilter(obj, event)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._combo.popup_closed()


class LanguageCombo(QComboBox):
    """Single language. Optional first entry with an empty value ('none' / 'off')."""

    def __init__(self, empty_label: str | None = None, include_undetermined: bool = False,
                 parent=None):
        super().__init__(parent)
        if empty_label:
            self._add(empty_label, "", "off none")
        if include_undetermined:
            self._add(display(UNDETERMINED[0]), UNDETERMINED[0], search_text(UNDETERMINED[0]))
        for code, _ in LANGUAGES:
            self._add(display(code), code, search_text(code))
        self._popup = _SearchPopup(self, multi=False)

    def _add(self, label: str, code: str, search: str):
        self.addItem(label, code)
        self.setItemData(self.count() - 1, search, SEARCH_ROLE)

    def showPopup(self):
        self._popup.open()

    def hidePopup(self):
        self._popup.hide()

    def popup_closed(self):
        pass

    def value(self) -> str:
        return self.currentData() or ""

    def set_value(self, code: str):
        code = normalize(code)
        idx = self.findData(code)
        if idx < 0 and code:                 # a code we don't list: keep it, don't lose it
            self._add(code, code, code)
            idx = self.count() - 1
        self.setCurrentIndex(max(idx, 0))


class MultiLanguageCombo(QComboBox):
    """Checkable list that stays open while ticking; the field shows the picked names."""

    changed = Signal()

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self._model = QStandardItemModel(self)
        for code, _ in LANGUAGES:
            self._model.appendRow(self._make_item(code))
        self.setModel(self._model)

        # An editable-but-read-only line edit is the simplest way to show free summary text
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setPlaceholderText(placeholder)
        self.lineEdit().installEventFilter(self)
        self._model.dataChanged.connect(self._on_changed)
        # QComboBox writes the "current item" into the line edit on its own; put the summary back
        self.currentIndexChanged.connect(lambda _: self._refresh_text())
        self._popup = _SearchPopup(self, multi=True)
        self._refresh_text()

    @staticmethod
    def _make_item(code: str) -> QStandardItem:
        item = QStandardItem(display(code))
        item.setData(code, CODE_ROLE)
        item.setData(search_text(code), SEARCH_ROLE)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        item.setData(Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
        return item

    def eventFilter(self, obj, event):
        if obj is self.lineEdit() and event.type() == QEvent.Type.MouseButtonRelease:
            if self.isEnabled():
                self.showPopup()
            return True
        return super().eventFilter(obj, event)

    def showPopup(self):
        self._popup.open()

    def hidePopup(self):
        self._popup.hide()

    def popup_closed(self):
        self._refresh_text()

    def _on_changed(self, *args):
        self._refresh_text()
        self.changed.emit()

    def _refresh_text(self):
        self.lineEdit().setText(", ".join(display(c) for c in self.values()))
        self.lineEdit().setCursorPosition(0)
        # Codes can come from a hand-edited preset: never let Qt read them as markup
        names = [display(c) for c in self.values()]
        self.setToolTip(plain_tooltip("\n".join(names)) if names else "")

    def values(self) -> list[str]:
        out = []
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                out.append(item.data(CODE_ROLE))
        return out

    def set_values(self, codes: list[str]):
        wanted = [normalize(c) for c in codes if c and c.strip()]
        known = {self._model.item(r).data(CODE_ROLE) for r in range(self._model.rowCount())}
        for code in wanted:
            if code not in known:            # keep codes we don't list (e.g. from an old preset)
                self._model.appendRow(self._make_item(code))
                known.add(code)
        self._model.blockSignals(True)
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            state = Qt.CheckState.Checked if item.data(CODE_ROLE) in wanted else Qt.CheckState.Unchecked
            item.setCheckState(state)
        self._model.blockSignals(False)
        self._refresh_text()
        self.changed.emit()
