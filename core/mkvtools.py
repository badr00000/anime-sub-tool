import json
import re
import sys
import subprocess
from pathlib import Path
from typing import Callable, Optional

from core.models import FileInfo, Track, TrackType, ProcessingResult, ProcessingStatus
from core.constants import MKVMERGE_SUCCESS, MKVMERGE_WARNING, MKVMERGE_ERROR
from utils.logger import get_logger

logger = get_logger(__name__)

class MKVToolsWrapper:
    """Wrapper around mkvmerge and mkvpropedit binaries."""

    def __init__(self, mkvtoolnix_path: Optional[str] = None):
        # 1. First, check for bundled binaries in the 'bin' folder
        if hasattr(sys, '_MEIPASS'):
            # Running as bundled PyInstaller EXE
            base_dir = Path(sys._MEIPASS)
        else:
            # Running from source (core/../bin)
            base_dir = Path(__file__).resolve().parent.parent

        bundled_mkvmerge = base_dir / "bin" / "mkvmerge.exe"
        bundled_mkvpropedit = base_dir / "bin" / "mkvpropedit.exe"
        
        if bundled_mkvmerge.exists() and bundled_mkvpropedit.exists():
            self.mkvmerge_path = bundled_mkvmerge
            self.mkvpropedit_path = bundled_mkvpropedit
        else:
            # 2. Fallback to system installation
            base_path = Path(mkvtoolnix_path) if mkvtoolnix_path else Path(r"C:\Program Files\MKVToolNix")
            self.mkvmerge_path = base_path / "mkvmerge.exe"
            self.mkvpropedit_path = base_path / "mkvpropedit.exe"

    def validate_installation(self) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                [str(self.mkvmerge_path), "--version"], 
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            if result.returncode == 0:
                return True, result.stdout.strip()
            return False, "Failed to run mkvmerge"
        except FileNotFoundError:
            return False, "mkvmerge not found"

    def identify(self, file_path: str) -> FileInfo:
        """Run 'mkvmerge -J file_path' and parse JSON output."""
        cmd = [str(self.mkvmerge_path), "-J", str(file_path)]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True, encoding='utf-8',
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            data = json.loads(result.stdout)
            
            tracks = []
            for track_data in data.get("tracks", []):
                t_type = track_data.get("type")
                if t_type == "video":
                    track_type = TrackType.VIDEO
                elif t_type == "audio":
                    track_type = TrackType.AUDIO
                elif t_type == "subtitles":
                    track_type = TrackType.SUBTITLE
                else:
                    track_type = TrackType.UNKNOWN
                    
                props = track_data.get("properties", {})
                
                track = Track(
                    id=track_data.get("id"),
                    type=track_type,
                    codec=track_data.get("codec"),
                    language=props.get("language", "und"),
                    name=props.get("track_name", ""),
                    is_default=props.get("default_track", False),
                    is_forced=props.get("forced_track", False)
                )
                tracks.append(track)
                
            return FileInfo(filepath=Path(file_path), tracks=tracks)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to identify {file_path}: {e.stderr}")
            return FileInfo(filepath=Path(file_path), tracks=[])
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON output for {file_path}: {e}")
            return FileInfo(filepath=Path(file_path), tracks=[])

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
        
        cmd = [str(self.mkvmerge_path), "-o", str(output_path)]
        
        # Audio tracks selection
        if audio_track_ids is not None:
            if not audio_track_ids:
                cmd.append("-A") # no audio
            else:
                cmd.extend(["-a", ",".join(map(str, audio_track_ids))])
                
        # Subtitles from original video
        if sub_track_ids is not None:
            if not sub_track_ids:
                cmd.append("-S") # no subs
            else:
                cmd.extend(["-s", ",".join(map(str, sub_track_ids))])
                
        # Edit existing track metadata (Must come BEFORE the video_path)
        if edit_track_id is not None:
            cmd.extend(["--language", f"{edit_track_id}:{edit_new_lang}"])
            if edit_new_name:
                cmd.extend(["--track-name", f"{edit_track_id}:{edit_new_name}"])
            
        cmd.append(str(video_path))
        
        # New subtitle file
        if subtitle_path:
            cmd.extend(["--language", f"0:{sub_language}"])
            cmd.extend(["--track-name", f"0:{sub_name}"])
            if sub_default:
                cmd.extend(["--default-track", "0:yes"])
            else:
                cmd.extend(["--default-track", "0:no"])
            if sub_offset_ms:
                cmd.extend(["--sync", f"0:{int(sub_offset_ms)}"])
            if sub_charset:
                cmd.extend(["--sub-charset", f"0:{sub_charset}"])
            cmd.append(str(subtitle_path))

        logger.info(f"Running mkvmerge: {' '.join(cmd)}")
        
        try:
            # Read stdout line by line. stderr is merged into stdout so it can never
            # fill its pipe and block mkvmerge, and so its error text is captured.
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )

            progress_pattern = re.compile(r"Progress: (\d+)%")
            problems: list[str] = []

            for line in iter(process.stdout.readline, ''):
                match = progress_pattern.search(line)
                if match:
                    if progress_callback:
                        progress_callback(int(match.group(1)))
                    continue
                text = line.strip()
                if text.startswith(("Error:", "Warning:")):
                    problems.append(text)

            process.wait()

            status = ProcessingStatus.COMPLETED
            if process.returncode == MKVMERGE_ERROR:
                status = ProcessingStatus.FAILED
            elif process.returncode == MKVMERGE_WARNING:
                status = ProcessingStatus.COMPLETED_WITH_WARNINGS

            errors = [p for p in problems if p.startswith("Error:")]
            warnings = [p for p in problems if p.startswith("Warning:")]
            if errors:
                message = " | ".join(errors)
                logger.error(f"mkvmerge failed for {video_path}: {message}")
            else:
                message = f"mkvmerge exited with code {process.returncode}"
            for w in warnings:
                logger.warning(f"mkvmerge: {w}")

            return ProcessingResult(
                status=status,
                output_path=Path(output_path),
                message=message,
                warnings=warnings
            )
            
        except Exception as e:
            logger.error(f"Error executing mkvmerge: {e}")
            return ProcessingResult(
                status=ProcessingStatus.FAILED,
                output_path=Path(output_path),
                message=str(e)
            )

    def edit_properties(self, file_path: str, track_edits: list[dict]) -> bool:
        """Use mkvpropedit for in-place property changes.
        track_edits format: [{'selector': 'track:s1', 'properties': {'name': 'Arabic', 'language': 'ara', 'flag-default': '1'}}]
        """
        cmd = [str(self.mkvpropedit_path), str(file_path)]
        
        for edit in track_edits:
            cmd.extend(["--edit", edit['selector']])
            for prop, value in edit['properties'].items():
                cmd.extend(["--set", f"{prop}={value}"])
                
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            if result.returncode not in (0, 1):  # 0 = ok, 1 = warnings
                logger.error(f"Failed to edit properties for {file_path}: {(result.stdout or result.stderr).strip()}")
                return False
            return True
        except OSError as e:
            logger.error(f"Could not run mkvpropedit for {file_path}: {e}")
            return False
