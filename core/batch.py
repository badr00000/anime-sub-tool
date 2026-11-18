import os
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Callable, Optional

from core.constants import MAX_PARALLEL_WORKERS, MIN_PARALLEL_WORKERS
from core.models import EpisodeMatch, ProcessingOptions, BatchResult, ProcessingStatus, ProcessingResult
from core.processor import EpisodeProcessor, partial_path_for
from utils.logger import get_logger

logger = get_logger(__name__)

_LOG_LEVELS = {"ERROR": logger.error, "WARNING": logger.warning}
_POLL_SECONDS = 0.25


class BatchProcessor:
    def __init__(self, processor: EpisodeProcessor, max_workers: int = 4):
        self.processor = processor
        self.max_workers = max(MIN_PARALLEL_WORKERS, min(MAX_PARALLEL_WORKERS, int(max_workers)))
        self._cancel_event = threading.Event()

    def _duplicate_outputs(self, matches: list[EpisodeMatch]) -> dict[int, str]:
        """Index -> message for episodes whose output another episode already takes
        ('ep01.mp4' and 'ep01.mkv' both become 'ep01.mkv')."""
        seen: dict[str, str] = {}
        clashes: dict[int, str] = {}
        for index, match in enumerate(matches):
            output = self.processor.output_path(match.video.filepath)
            key = os.path.normcase(str(output.resolve()))
            if key in seen:
                clashes[index] = (f"{match.video.filename} would write the same output file as "
                                  f"{seen[key]} ({output.name}); rename one of them.")
            else:
                seen[key] = match.video.filename
        return clashes

    def process_all(self, matches: list[EpisodeMatch], options: ProcessingOptions,
                    progress_callback: Optional[Callable[[str, int, int], None]] = None,
                    log_callback: Optional[Callable[[str, str], None]] = None) -> BatchResult:

        total_episodes = len(matches)
        completed_episodes = 0
        results: list[Optional[ProcessingResult]] = [None] * total_episodes

        def _log(msg: str, lvl: str = "INFO"):
            # 'echoed' tells the console handler the caller already shows this line
            _LOG_LEVELS.get(lvl, logger.info)(msg, extra={"echoed": log_callback is not None})
            if log_callback:
                log_callback(msg, lvl)

        # No output may land on a file that is an input of this batch
        inputs = [m.video.filepath for m in matches]
        inputs += [m.subtitle.filepath for m in matches if m.subtitle]
        self.processor.protect(inputs)
        clashes = self._duplicate_outputs(matches)

        def _process_single(index: int, match: EpisodeMatch) -> ProcessingResult:
            if self._cancel_event.is_set():
                return ProcessingResult(status=ProcessingStatus.CANCELLED, output_path=None, message="Cancelled")

            episode_num = match.video.episode_num or "?"
            if index in clashes:
                _log(f"Failed processing episode {episode_num}: {clashes[index]}", "ERROR")
                return ProcessingResult(status=ProcessingStatus.FAILED, message=clashes[index])

            def local_progress(prog: int):
                # Approximation: files differ in size and run in parallel
                overall = int(((completed_episodes * 100) + prog) / total_episodes)
                if progress_callback:
                    progress_callback(episode_num, prog, overall)

            try:
                if options.dry_run:
                    res = self.processor.dry_run(match)
                else:
                    _log(f"Starting processing for episode {episode_num}")
                    res = self.processor.process(match, progress_callback=local_progress,
                                                 cancel_event=self._cancel_event)
            except Exception as e:
                logger.exception(f"Unexpected error on episode {episode_num}")
                res = ProcessingResult(status=ProcessingStatus.FAILED, output_path=None, message=str(e))

            for warning in res.warnings:
                _log(f"Episode {episode_num}: {warning}", "WARNING")
            if res.status == ProcessingStatus.FAILED:
                _log(f"Failed processing episode {episode_num}: {res.message}", "ERROR")
            elif res.status == ProcessingStatus.SKIPPED:
                _log(f"Skipped episode {episode_num}: {res.message}", "WARNING")
            elif res.status == ProcessingStatus.CANCELLED:
                _log(f"Cancelled episode {episode_num}", "WARNING")
            elif options.dry_run:
                _log(f"[DRY RUN] Episode {episode_num} would be written to {res.output_path}")
            elif res.status == ProcessingStatus.COMPLETED_WITH_WARNINGS:
                _log(f"Completed episode {episode_num} with warnings", "WARNING")
            else:
                _log(f"Completed processing for episode {episode_num}")
            return res

        executor = ThreadPoolExecutor(max_workers=self.max_workers)
        try:
            future_to_index = {executor.submit(_process_single, i, match): i
                               for i, match in enumerate(matches)}

            pending = set(future_to_index)
            while pending:
                # Wake up regularly: on Windows a thread blocked without a timeout
                # does not see Ctrl+C until an episode happens to finish.
                done, pending = wait(pending, timeout=_POLL_SECONDS, return_when=FIRST_COMPLETED)
                for future in sorted(done, key=future_to_index.get):
                    index = future_to_index[future]
                    match = matches[index]
                    res = future.result()
                    res.video_name = match.video.filename
                    results[index] = res
                    completed_episodes += 1

                    if progress_callback:
                        # Update overall progress at the end of each episode
                        overall = int((completed_episodes * 100) / total_episodes)
                        progress_callback(match.video.episode_num or "?", 100, overall)
        except BaseException:
            # Ctrl+C (KeyboardInterrupt) or any other abort: a plain `with` block would
            # wait for every queued episode to run. Stop everything instead.
            self.cancel(force=True)
            executor.shutdown(wait=True, cancel_futures=True)
            self._remove_partials(matches)
            raise
        executor.shutdown(wait=True)

        def count(*statuses: ProcessingStatus) -> int:
            return sum(1 for r in results if r.status in statuses)

        return BatchResult(
            total=total_episodes,
            successful=count(ProcessingStatus.COMPLETED, ProcessingStatus.COMPLETED_WITH_WARNINGS),
            failed=count(ProcessingStatus.FAILED),
            cancelled=count(ProcessingStatus.CANCELLED),
            skipped=count(ProcessingStatus.SKIPPED),
            dry_run=options.dry_run,
            results=results,
        )

    def _remove_partials(self, matches: list[EpisodeMatch]) -> None:
        """Best effort: delete unfinished outputs left by an aborted batch."""
        for match in matches:
            try:
                partial_path_for(self.processor.output_path(match.video.filepath)).unlink(missing_ok=True)
            except (OSError, ValueError):
                pass

    def cancel(self, force: bool = False):
        """Stop the batch: episodes not started yet are cancelled, running ones
        finish. force=True also stops the running mkvmerge processes."""
        self._cancel_event.set()
        if force:
            self.processor.mkv_tools.terminate_all()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()
