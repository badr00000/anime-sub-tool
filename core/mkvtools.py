import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional

from core.models import FileInfo, Track, TrackType, ProcessingResult, ProcessingStatus
from core.constants import MKVMERGE_ERROR, MKVMERGE_WARNING, MKVTOOLNIX_DEFAULT_PATHS
from utils.logger import get_logger
from utils.paths import resource_path

logger = get_logger(__name__)

_EXE_NAME = "mkvmerge.exe" if os.name == "nt" else "mkvmerge"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_PROGRESS = re.compile(r"Progress: (\d+)%")


def locate_mkvmerge(custom_dir: Optional[str] = None) -> Path:
    """Pick the mkvmerge to run.

    A folder set in Settings wins when it really contains mkvmerge; an empty
    setting means the copy bundled with the app; a system installation is only
    the last resort.
    """
    custom_dir = (custom_dir or "").strip()
    if custom_dir:
        candidate = Path(custom_dir) / _EXE_NAME
        if candidate.is_file():
            return candidate
        logger.warning(f"No {_EXE_NAME} in the configured MKVToolNix folder '{custom_dir}'; "
                       "using the bundled copy instead.")

    bundled = resource_path("bin", "mkvmerge.exe")
    if bundled.is_file():
        return bundled

    on_path = shutil.which("mkvmerge")
    if on_path:
        return Path(on_path)
    for folder in MKVTOOLNIX_DEFAULT_PATHS:
        candidate = Path(folder) / _EXE_NAME
        if candidate.is_file():
            return candidate
    return bundled  # does not exist; validate_installation() reports it by path


def has_mkvmerge(folder: str) -> bool:
    """True when `folder` contains a mkvmerge executable."""
    return bool(folder and folder.strip()) and (Path(folder.strip()) / _EXE_NAME).is_file()


def _path_arg(path) -> str:
    """A file path as a mkvmerge argument: always absolute.

    mkvmerge reads an argument starting with '@' as an option file and one
    starting with '-' as an option, so a bare file name must never reach it.
    """
    arg = str(Path(path).resolve())
    if arg.startswith(("@", "-")) or not Path(arg).is_absolute():
        raise ValueError(f"Unsafe path for mkvmerge: {path}")
    return arg


class MKVToolsWrapper:
    """Wrapper around the mkvmerge binary."""

    def __init__(self, mkvtoolnix_path: Optional[str] = None):
        self.mkvmerge_path = locate_mkvmerge(mkvtoolnix_path)
        self._running: set[subprocess.Popen] = set()
        self._lock = threading.Lock()
        self._terminated = threading.Event()

    def _start_error(self, error: Exception) -> str:
        return f"mkvmerge could not be started ({self.mkvmerge_path}): {error}"

    def validate_installation(self) -> tuple[bool, str]:
        """(True, version line) or (False, what is wrong, naming the path tried)."""
        try:
            result = subprocess.run(
                [str(self.mkvmerge_path), "--version"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW, timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as e:
            return False, self._start_error(e)
        if result.returncode == 0:
            return True, result.stdout.strip()
        detail = (result.stdout or result.stderr or "").strip()
        return False, (f"mkvmerge at {self.mkvmerge_path} exited with code "
                       f"{result.returncode}: {detail}")

    def identify(self, file_path: str) -> FileInfo:
        """Run 'mkvmerge -J file' and parse the JSON. On failure FileInfo.error is set."""
        info = FileInfo(filepath=Path(file_path))
        try:
            cmd = [str(self.mkvmerge_path), "-J", _path_arg(file_path)]
            result = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW,
            )
        except (OSError, ValueError) as e:
            info.error = self._start_error(e) if isinstance(e, OSError) else str(e)
            logger.error(info.error)
            return info

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            data = None

        if result.returncode >= MKVMERGE_ERROR or not isinstance(data, dict):
            # mkvmerge reports identification errors on stdout, not stderr
            errors = data.get("errors") if isinstance(data, dict) else None
            detail = " | ".join(str(e) for e in errors) if errors else \
                (result.stdout or result.stderr or "").strip()
            info.error = (f"mkvmerge could not read {Path(file_path).name} "
                          f"(exit code {result.returncode}): {detail}")
            logger.error(info.error)
            return info

        container = data.get("container") or {}
        if container.get("recognized") is False or container.get("supported") is False:
            info.error = f"{Path(file_path).name} is not a media file mkvmerge can read."
            logger.error(info.error)
            return info

        types = {"video": TrackType.VIDEO, "audio": TrackType.AUDIO, "subtitles": TrackType.SUBTITLE}
        for track_data in data.get("tracks", []):
            props = track_data.get("properties", {})
            info.tracks.append(Track(
                id=track_data.get("id"),
                type=types.get(track_data.get("type"), TrackType.UNKNOWN),
                codec=track_data.get("codec") or "",
                language=props.get("language", "und"),
                name=props.get("track_name", ""),
                is_default=props.get("default_track", False),
                is_forced=props.get("forced_track", False),
            ))
        return info

    def terminate_all(self) -> None:
        """Stop every running mkvmerge (used when the app is closing)."""
        self._terminated.set()
        with self._lock:
            running = list(self._running)
        for process in running:
            try:
                process.terminate()
            except OSError:
                pass

    def merge(self, video_path: str, output_path: str,
              subtitle_path: Optional[str] = None,
              audio_track_ids: Optional[list[int]] = None,
              sub_track_ids: Optional[list[int]] = None,
              sub_language: str = 'ara',
              sub_name: str = 'Arabic',
              sub_default: bool = True,
              edit_track_id: Optional[int] = None,
              edit_new_lang: str = "ara",
              edit_new_name: str = "Arabic",
              sub_offset_ms: int = 0,
              sub_charset: Optional[str] = None,
              progress_callback: Optional[Callable[[int], None]] = None) -> ProcessingResult:
        """Build and execute mkvmerge command. Parse real-time 'Progress: XX%' from stdout."""
        try:
            video_arg = _path_arg(video_path)
            output_arg = _path_arg(output_path)
            subtitle_arg = _path_arg(subtitle_path) if subtitle_path else None
        except ValueError as e:
            return ProcessingResult(status=ProcessingStatus.FAILED, output_path=Path(output_path),
                                    message=str(e))
        if output_arg.lower() in (video_arg.lower(), (subtitle_arg or "").lower()):
            return ProcessingResult(status=ProcessingStatus.FAILED, output_path=Path(output_path),
                                    message="Refusing to write the output over an input file.")

        # The messages are read as UTF-8 below, whatever the console code page is
        cmd = [str(self.mkvmerge_path), "--output-charset", "UTF-8", "-o", output_arg]

        # Audio tracks selection
        if audio_track_ids is not None:
            if not audio_track_ids:
                cmd.append("-A")  # no audio
            else:
                cmd.extend(["-a", ",".join(map(str, audio_track_ids))])

        # Subtitles from original video
        if sub_track_ids is not None:
            if not sub_track_ids:
                cmd.append("-S")  # no subs
            else:
                cmd.extend(["-s", ",".join(map(str, sub_track_ids))])

        # Edit existing track metadata (Must come BEFORE the video_path)
        if edit_track_id is not None:
            cmd.extend(["--language", f"{edit_track_id}:{edit_new_lang}"])
            if edit_new_name:
                cmd.extend(["--track-name", f"{edit_track_id}:{edit_new_name}"])

        cmd.append(video_arg)

        # New subtitle file
        if subtitle_arg:
            cmd.extend(["--language", f"0:{sub_language}"])
            cmd.extend(["--track-name", f"0:{sub_name}"])
            cmd.extend(["--default-track", "0:yes" if sub_default else "0:no"])
            if sub_offset_ms:
                cmd.extend(["--sync", f"0:{int(sub_offset_ms)}"])
            if sub_charset:
                cmd.extend(["--sub-charset", f"0:{sub_charset}"])
            cmd.append(subtitle_arg)

        logger.info(f"Running mkvmerge: {subprocess.list2cmdline(cmd)}")

        try:
            # Read stdout line by line. stderr is merged into stdout so it can never
            # fill its pipe and block mkvmerge, and so its error text is captured.
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=_NO_WINDOW,
            )
        except OSError as e:
            message = self._start_error(e)
            logger.error(message)
            return ProcessingResult(status=ProcessingStatus.FAILED, output_path=Path(output_path),
                                    message=message)

        with self._lock:
            self._running.add(process)
        try:
            problems: list[str] = []
            for line in iter(process.stdout.readline, ''):
                match = _PROGRESS.search(line)
                if match:
                    if progress_callback:
                        progress_callback(int(match.group(1)))
                    continue
                text = line.strip()
                if text.startswith(("Error:", "Warning:")):
                    problems.append(text)
            process.wait()
        except Exception as e:
            process.kill()
            logger.error(f"Error while running mkvmerge: {e}")
            return ProcessingResult(status=ProcessingStatus.FAILED, output_path=Path(output_path),
                                    message=f"mkvmerge failed: {e}")
        finally:
            process.stdout.close()
            with self._lock:
                self._running.discard(process)

        if self._terminated.is_set() and process.returncode not in (0, MKVMERGE_WARNING):
            return ProcessingResult(status=ProcessingStatus.CANCELLED, output_path=Path(output_path),
                                    message="Cancelled")

        errors = [p for p in problems if p.startswith("Error:")]
        warnings = [p for p in problems if p.startswith("Warning:")]
        if process.returncode == 0:
            status = ProcessingStatus.COMPLETED
        elif process.returncode == MKVMERGE_WARNING:
            status = ProcessingStatus.COMPLETED_WITH_WARNINGS
        else:
            status = ProcessingStatus.FAILED

        if errors:
            message = " | ".join(errors)
        else:
            message = f"mkvmerge exited with code {process.returncode}"
        if status == ProcessingStatus.FAILED:
            logger.error(f"mkvmerge failed for {video_path}: {message}")
        for w in warnings:
            logger.warning(f"mkvmerge: {w}")

        return ProcessingResult(status=status, output_path=Path(output_path),
                                message=message, warnings=warnings)
