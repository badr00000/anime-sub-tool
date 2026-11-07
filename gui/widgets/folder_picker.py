"""Folder Picker Widget — Path input with browse button and drag-drop."""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton, QFileDialog, QLabel, QVBoxLayout
from PySide6.QtCore import Qt, Signal
from pathlib import Path


class FolderPicker(QWidget):
    """Folder selection widget with browse button, drag-drop, and validation."""

    path_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("folderPicker")
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Label
        label = QLabel("Folder Path")
        label.setStyleSheet("font-weight: 600; color: #94a3b8; font-size: 12px;")

        # Input row
        row = QHBoxLayout()
        row.setSpacing(8)

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Select folder containing video and subtitle files...")
        self.path_edit.setMinimumHeight(40)
        self.path_edit.textChanged.connect(self._on_text_changed)

        self.browse_btn = QPushButton("Browse")
        self.browse_btn.setFixedHeight(40)
        self.browse_btn.setFixedWidth(90)
        self.browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_btn.clicked.connect(self._browse)

        row.addWidget(self.path_edit, 1)
        row.addWidget(self.browse_btn)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 11px; color: #64748b;")

        layout.addWidget(label)
        layout.addLayout(row)
        layout.addWidget(self.status_label)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Folder", self.path_edit.text() or ""
        )
        if folder:
            self.path_edit.setText(folder)

    def _on_text_changed(self, text: str):
        path = Path(text.strip()) if text.strip() else None
        if path and path.exists() and path.is_dir():
            # Count relevant files
            videos = sum(1 for f in path.iterdir()
                         if f.is_file() and f.suffix.lower() in {'.mkv', '.mp4', '.webm', '.avi'})
            subs = sum(1 for f in path.iterdir()
                       if f.is_file() and f.suffix.lower() in {'.ass', '.ssa', '.srt', '.vtt', '.sub'})
            self.status_label.setText(f"Found {videos} video(s), {subs} subtitle(s)")
            self.status_label.setStyleSheet("font-size: 11px; color: #10b981;")
            self.path_edit.setStyleSheet("border-color: #10b981;")
        elif text.strip():
            self.status_label.setText("Folder not found")
            self.status_label.setStyleSheet("font-size: 11px; color: #ef4444;")
            self.path_edit.setStyleSheet("border-color: #ef4444;")
        else:
            self.status_label.setText("")
            self.path_edit.setStyleSheet("")

        self.path_changed.emit(text)

    def get_path(self) -> str:
        return self.path_edit.text().strip()

    def set_path(self, path: str):
        self.path_edit.setText(path)

    # Drag and drop support
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if Path(url.toLocalFile()).is_dir():
                    event.acceptProposedAction()
                    self.path_edit.setStyleSheet("border: 2px solid #6366f1;")
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        self.path_edit.setStyleSheet("")

    def dropEvent(self, event):
        self.path_edit.setStyleSheet("")
        for url in event.mimeData().urls():
            local_path = url.toLocalFile()
            if Path(local_path).is_dir():
                self.path_edit.setText(local_path)
                break
