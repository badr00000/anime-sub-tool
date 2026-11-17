"""Message boxes that always show their text as plain text.

QMessageBox guesses the format: a file name or mkvmerge message containing
markup would otherwise be rendered as rich text (images and links included).
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox


def _show(parent, icon, title: str, text: str, buttons) -> int:
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(text)
    box.setStandardButtons(buttons)
    return box.exec()


def info(parent, title: str, text: str) -> None:
    _show(parent, QMessageBox.Icon.Information, title, text, QMessageBox.StandardButton.Ok)


def warn(parent, title: str, text: str) -> None:
    _show(parent, QMessageBox.Icon.Warning, title, text, QMessageBox.StandardButton.Ok)


def error(parent, title: str, text: str) -> None:
    _show(parent, QMessageBox.Icon.Critical, title, text, QMessageBox.StandardButton.Ok)


def confirm(parent, title: str, text: str) -> bool:
    answer = _show(parent, QMessageBox.Icon.Question, title, text,
                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    return answer == QMessageBox.StandardButton.Yes
