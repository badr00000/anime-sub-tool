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
from core.matcher import match_files, scan_folder, set_manual_subtitle, unused_subtitles
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

    def scan_and_match(self, folder_path, subtitle_language: Optional[str] = None) -> ScanResult:
        """Scan a folder and match video files to subtitle files.

        subtitle_language: the language the added track will be labelled with
        (None = the one saved in Settings). A subtitle whose name says that
        language is preferred; one that says another language is flagged."""
        path = Path(folder_path).resolve()
        if subtitle_language is None:
            subtitle_language = self.config.subtitle_language

        videos, subtitles = scan_folder(path)
        # Every text subtitle, not only the matched ones: the Preview step lets
        # the user pair any of them by hand.
        for sub in subtitles:
            if sub.filepath.suffix.lower() in TEXT_SUBTITLE_EXTENSIONS:
                sub.encoding = describe_encoding(detect_file_encoding(sub.filepath))

        result = ScanResult(folder_path=path, video_files=videos, subtitle_files=subtitles)
        self.rematch(result, subtitle_language)
        return result

    @staticmethod
    def rematch(scan_result: ScanResult, subtitle_language: str) -> ScanResult:
        """Match the scanned files again (for another subtitle language)."""
        matches, unmatched_videos, unmatched_subtitles = match_files(
            scan_result.video_files, scan_result.subtitle_files, subtitle_language)
        scan_result.matches = matches
        scan_result.unmatched_videos = unmatched_videos
        scan_result.unmatched_subtitles = unmatched_subtitles
        return scan_result

    @staticmethod
    def set_manual_subtitle(scan_result: ScanResult, index: int, subtitle,
                            subtitle_language: str) -> Optional[int]:
        """Pair episode `index` with the subtitle the user picked (None = none) and
        update the unmatched lists. Returns the episode the subtitle was moved from."""
        moved_from = set_manual_subtitle(scan_result.matches, index, subtitle, subtitle_language)
        scan_result.unmatched_videos = [m.video for m in scan_result.matches if m.subtitle is None]
        scan_result.unmatched_subtitles = unused_subtitles(scan_result.matches,
                                                           scan_result.subtitle_files)
        return moved_from

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
