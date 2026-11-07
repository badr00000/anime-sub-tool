"""
Anime Subtitle Automation Tool v2.0 — Processing Engine

High-level orchestrator that ties together scanning, matching, 
previewing, and batch processing.
"""

from typing import Callable, Optional
from pathlib import Path

from core.models import (
    AppConfig, ScanResult, PreviewData, ProcessingOptions,
    BatchResult, EpisodeMatch, ProcessingResult
)
from core.matcher import scan_folder, match_files, auto_detect_series_name
from core.mkvtools import MKVToolsWrapper
from core.processor import EpisodeProcessor
from core.batch import BatchProcessor
from utils.logger import get_logger

logger = get_logger(__name__)


class ProcessingEngine:
    """High-level API used by GUI and CLI."""

    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or AppConfig()
        self.mkv_tools = MKVToolsWrapper(self.config.mkvtoolnix_path)

    def scan_and_match(self, folder_path: str, series_name: str = "") -> ScanResult:
        """Scan a folder and match video files to subtitle files."""
        path = Path(folder_path) if isinstance(folder_path, str) else folder_path

        videos, subtitles = scan_folder(path)

        matches, unmatched_videos, unmatched_subtitles = match_files(videos, subtitles)

        detected_series = series_name
        if not detected_series:
            detected_series = auto_detect_series_name(videos + subtitles)

        return ScanResult(
            folder_path=path,
            series_name=detected_series,
            video_files=videos,
            subtitle_files=subtitles,
            matches=matches,
            unmatched_videos=unmatched_videos,
            unmatched_subtitles=unmatched_subtitles,
        )

    def generate_preview(self, scan_result: ScanResult, options: ProcessingOptions) -> PreviewData:
        """Generate preview data showing what operations will be performed."""
        processor = EpisodeProcessor(self.mkv_tools, options)

        previews = []
        all_operations = []
        for match in scan_result.matches:
            ep_preview = processor.generate_preview(match)
            previews.append(ep_preview)
            all_operations.extend(ep_preview.operations)

        return PreviewData(
            episodes=previews,
            operations=all_operations,
            total_operations=len(all_operations),
        )

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

        return batch_processor.process_all(
            matches=scan_result.matches,
            options=options,
            progress_callback=progress_callback,
            log_callback=log_callback,
        )

    def cancel(self) -> None:
        """Stop a running batch: episodes not started yet are skipped, running ones finish."""
        batch = getattr(self, "_active_batch", None)
        if batch is not None:
            batch.cancel()

    def process_single(self, match: EpisodeMatch, options: ProcessingOptions) -> ProcessingResult:
        """Process a single episode."""
        processor = EpisodeProcessor(self.mkv_tools, options)
        return processor.process(match)
