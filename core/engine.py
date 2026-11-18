"""
Anime Subtitle Automation Tool v2.0 — Processing Engine

High-level orchestrator that ties together scanning, matching,
previewing, and batch processing.
"""

from typing import Callable, Optional
from pathlib import Path

from core.constants import TEXT_SUBTITLE_EXTENSIONS
from core.models import (
    AppConfig, ScanResult, PreviewData, ProcessingOptions, BatchResult,
)
from core.matcher import scan_folder, match_files
from core.mkvtools import MKVToolsWrapper
from core.processor import EpisodeProcessor
from core.batch import BatchProcessor
from core.subtitles import describe_encoding, detect_file_encoding
from utils.logger import get_logger
from utils.paths import resolve_output_dir

logger = get_logger(__name__)


class ProcessingEngine:
    """High-level API used by GUI and CLI."""

    def __init__(self, config: Optional[AppConfig] = None,
                 mkv_tools: Optional[MKVToolsWrapper] = None):
        self.config = config or AppConfig()
        self.mkv_tools = mkv_tools or MKVToolsWrapper(self.config.mkvtoolnix_path)
        self._active_batch: Optional[BatchProcessor] = None
        self._cancel_requested = False

    def default_options(self) -> ProcessingOptions:
        return ProcessingOptions.from_config(self.config)

    def scan_and_match(self, folder_path) -> ScanResult:
        """Scan a folder and match video files to subtitle files."""
        path = Path(folder_path).resolve()

        videos, subtitles = scan_folder(path)
        matches, unmatched_videos, unmatched_subtitles = match_files(videos, subtitles)

        for match in matches:
            sub = match.subtitle
            if sub and sub.filepath.suffix.lower() in TEXT_SUBTITLE_EXTENSIONS:
                sub.encoding = describe_encoding(detect_file_encoding(sub.filepath))

        return ScanResult(
            folder_path=path,
            video_files=videos,
            subtitle_files=subtitles,
            matches=matches,
            unmatched_videos=unmatched_videos,
            unmatched_subtitles=unmatched_subtitles,
        )

    @staticmethod
    def output_dir(scan_result: ScanResult, options: ProcessingOptions) -> Path:
        """Folder the processed files of this scan are written to."""
        return resolve_output_dir(scan_result.folder_path, options.output_dir,
                                  options.create_output_folder, options.output_folder)

    def generate_preview(self, scan_result: ScanResult, options: ProcessingOptions) -> PreviewData:
        """Generate preview data showing what operations will be performed."""
        processor = EpisodeProcessor(self.mkv_tools, options)
        return PreviewData(episodes=[processor.generate_preview(m) for m in scan_result.matches])

    def process_batch(
        self,
        scan_result: ScanResult,
        options: ProcessingOptions,
        progress_callback: Optional[Callable] = None,
        log_callback: Optional[Callable] = None,
    ) -> BatchResult:
        """Process all matched episodes in parallel."""
        processor = EpisodeProcessor(self.mkv_tools, options)
        batch_processor = BatchProcessor(
            processor, max_workers=options.parallel_workers or self.config.default_workers
        )
        self._active_batch = batch_processor
        if self._cancel_requested:      # cancel() arrived before the batch existed
            batch_processor.cancel()

        try:
            return batch_processor.process_all(
                matches=scan_result.matches,
                options=options,
                progress_callback=progress_callback,
                log_callback=log_callback,
            )
        finally:
            self._active_batch = None
            self._cancel_requested = False

    def cancel(self, force: bool = False) -> None:
        """Stop a running batch: episodes not started yet are cancelled, running ones
        finish. force=True also stops the running mkvmerge processes and makes every
        later start attempt of this engine return CANCELLED."""
        self._cancel_requested = True
        if force:
            # Also covers a batch that is about to start (no _active_batch yet)
            self.mkv_tools.terminate_all()
        if self._active_batch is not None:
            self._active_batch.cancel(force=force)
