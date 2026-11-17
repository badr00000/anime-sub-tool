"""
Anime Subtitle Automation Tool v2.0 — Watch Folder Service

Uses watchdog to monitor a folder for new video or subtitle files.
Includes debouncing to prevent triggering multiple scans during a large file copy.
"""

import time
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PySide6.QtCore import QObject, Signal

from core.constants import SUBTITLE_EXTENSIONS, VIDEO_EXTENSIONS
from utils.logger import get_logger
from utils.paths import is_tool_output

logger = get_logger(__name__)


class DebouncedEventHandler(FileSystemEventHandler):
    """Event handler that debounces file system events."""
    
    def __init__(self, callback, debounce_seconds: float = 3.0):
        super().__init__()
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self._timer = None
        self._lock = threading.Lock()
        self.valid_extensions = VIDEO_EXTENSIONS | SUBTITLE_EXTENSIONS

    def on_any_event(self, event):
        if event.is_directory:
            return
            
        ext = Path(event.src_path).suffix.lower()
        # The tool's own outputs must not trigger a rescan of the folder they land in
        if ext not in self.valid_extensions or is_tool_output(Path(event.src_path)):
            return

        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            
            self._timer = threading.Timer(self.debounce_seconds, self._on_timeout)
            self._timer.daemon = True
            self._timer.start()

    def cancel(self):
        """Drop a pending notification (the watcher is being stopped)."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def _on_timeout(self):
        logger.info("Watchdog debounce timeout reached. Emitting change event.")
        self.callback()


class FolderWatcher(QObject):
    """QObject wrapper for watchdog Observer to integrate with PySide6 signals."""
    
    folder_changed = Signal()

    def __init__(self, folder_path: str, debounce_seconds: float = 3.0):
        super().__init__()
        self.folder_path = Path(folder_path)
        self.debounce_seconds = debounce_seconds
        self.observer = None
        self._handler = None

    def start(self):
        if self.observer is not None:
            return
            
        if not self.folder_path.exists() or not self.folder_path.is_dir():
            logger.error(f"Cannot watch invalid folder: {self.folder_path}")
            return
            
        logger.info(f"Starting FolderWatcher on {self.folder_path}")
        
        self._handler = DebouncedEventHandler(self._emit_signal, self.debounce_seconds)
        self.observer = Observer()
        self.observer.schedule(self._handler, str(self.folder_path), recursive=False)
        self.observer.start()
        
    def stop(self):
        if self.observer is not None:
            logger.info(f"Stopping FolderWatcher on {self.folder_path}")
            self.observer.stop()
            self.observer.join(timeout=5)
            self.observer = None
        if self._handler is not None:
            self._handler.cancel()
            self._handler = None
            
    def _emit_signal(self):
        # Must be called from the timer thread, safely emits to Qt event loop
        self.folder_changed.emit()
