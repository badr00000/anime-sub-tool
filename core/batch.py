from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional
import threading

from core.models import EpisodeMatch, ProcessingOptions, BatchResult, ProcessingStatus, ProcessingResult
from core.processor import EpisodeProcessor
from utils.logger import get_logger

logger = get_logger(__name__)

class BatchProcessor:
    def __init__(self, processor: EpisodeProcessor, max_workers: int = 4):
        self.processor = processor
        self.max_workers = max_workers
        self._cancel_event = threading.Event()

    def process_all(self, matches: list[EpisodeMatch], options: ProcessingOptions,
                    progress_callback: Optional[Callable[[str, int, int], None]] = None,
                    log_callback: Optional[Callable[[str, str], None]] = None) -> BatchResult:
        
        self._cancel_event.clear()
        
        total_episodes = len(matches)
        completed_episodes = 0
        
        results = []
        
        def _log(msg: str, lvl: str = "INFO"):
            if log_callback:
                log_callback(msg, lvl)
            else:
                if lvl == "ERROR":
                    logger.error(msg)
                elif lvl == "WARNING":
                    logger.warning(msg)
                else:
                    logger.info(msg)

        def _process_single(match: EpisodeMatch):
            if self._cancel_event.is_set():
                return ProcessingResult(status=ProcessingStatus.CANCELLED, output_path=None, message="Cancelled")
                
            episode_num = match.video.episode_num or "?"
            
            def local_progress(prog: int):
                # Calculate overall progress
                # Note: This is an approximation as files can be of different sizes and process in parallel
                overall = int(((completed_episodes * 100) + prog) / total_episodes)
                if progress_callback:
                    progress_callback(episode_num, prog, overall)
            
            _log(f"Starting processing for episode {episode_num}")
            
            try:
                if options.dry_run:
                    res = self.processor.dry_run(match)
                    _log(f"[DRY RUN] Episode {episode_num} would be written to {res.output_path}")
                    return res
                res = self.processor.process(match, progress_callback=local_progress)
                if res.status == ProcessingStatus.FAILED:
                    _log(f"Failed processing episode {episode_num}: {res.message}", "ERROR")
                elif res.status == ProcessingStatus.COMPLETED_WITH_WARNINGS:
                    detail = " | ".join(res.warnings) if res.warnings else res.message
                    _log(f"Completed episode {episode_num} with warnings: {detail}", "WARNING")
                else:
                    _log(f"Completed processing for episode {episode_num}")
                return res
            except Exception as e:
                _log(f"Failed processing episode {episode_num}: {str(e)}", "ERROR")
                return ProcessingResult(status=ProcessingStatus.FAILED, output_path=None, message=str(e))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_match = {executor.submit(_process_single, match): match for match in matches}
            
            for future in as_completed(future_to_match):
                match = future_to_match[future]
                res = future.result()
                results.append(res)
                completed_episodes += 1
                
                if progress_callback:
                    # Update overall progress at the end of each episode
                    overall = int((completed_episodes * 100) / total_episodes)
                    progress_callback(match.video.episode_num or "?", 100, overall)
                    
        successful = sum(1 for r in results if r.status in (ProcessingStatus.COMPLETED, ProcessingStatus.COMPLETED_WITH_WARNINGS))
        failed = sum(1 for r in results if r.status == ProcessingStatus.FAILED)
        cancelled = sum(1 for r in results if r.status == ProcessingStatus.CANCELLED)
        
        return BatchResult(
            total=total_episodes,
            successful=successful,
            failed=failed,
            cancelled=cancelled,
            results=results
        )

    def cancel(self):
        """Cancel processing."""
        self._cancel_event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()
