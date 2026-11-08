"""
Anime Subtitle Automation Tool v2.0 — Data Models

Unified data structures used by core engine, GUI, and CLI layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────

class TrackType(Enum):
    VIDEO = "video"
    AUDIO = "audio"
    SUBTITLE = "subtitles"
    UNKNOWN = "unknown"


class ProcessingStatus(Enum):
    PENDING = auto()
    SCANNING = auto()
    PROCESSING = auto()
    COMPLETED = auto()
    COMPLETED_WITH_WARNINGS = auto()
    FAILED = auto()
    SKIPPED = auto()
    CANCELLED = auto()


class MatchConfidence(Enum):
    EXACT = auto()
    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()
    NO_MATCH = auto()


# ──────────────────────────────────────────────────────────────
# Track & File Info
# ──────────────────────────────────────────────────────────────

@dataclass
class Track:
    """A single track inside an MKV container."""
    id: int
    type: TrackType
    codec: str = ""
    language: str = "und"
    name: str = ""
    is_default: bool = False
    is_forced: bool = False
    channels: int = 0
    pixel_width: int = 0
    pixel_height: int = 0


@dataclass
class FileInfo:
    """Metadata from mkvmerge -J."""
    filepath: Path
    tracks: list[Track] = field(default_factory=list)
    duration_ns: int = 0
    file_size: int = 0
    supported: bool = True


# ──────────────────────────────────────────────────────────────
# Episode Info & Matching
# ──────────────────────────────────────────────────────────────

@dataclass
class EpisodeInfo:
    """Parsed information from a media filename."""
    filepath: Path
    filename: str = ""
    episode_num: Optional[str] = None
    series_title: Optional[str] = None

    @property
    def episode_key(self) -> str:
        if self.episode_num is None:
            return ""
        try:
            return str(int(self.episode_num)).zfill(3)
        except ValueError:
            return self.episode_num.zfill(3)


@dataclass
class EpisodeMatch:
    """A matched pair of video file and subtitle file."""
    video: EpisodeInfo
    subtitle: Optional[EpisodeInfo] = None
    confidence: MatchConfidence = MatchConfidence.NO_MATCH
    score: float = 0.0

    @property
    def is_matched(self) -> bool:
        return self.subtitle is not None and self.confidence != MatchConfidence.NO_MATCH


# ──────────────────────────────────────────────────────────────
# Processing Options & Results
# ──────────────────────────────────────────────────────────────

@dataclass
class ProcessingOptions:
    """User-configurable processing options."""
    series_name: str = ""
    output_dir: Optional[Path] = None
    output_folder: str = "PROCESSED"
    output_suffix: str = ""
    subtitle_language: str = "ara"
    subtitle_name: str = "Arabic"
    set_default: bool = True
    create_backup: bool = True
    parallel_workers: int = 4
    dry_run: bool = False
    backup_originals: bool = True
    create_output_folder: bool = True
    keep_original: bool = False
    workers: int = 4
    keep_audio_langs: list[str] = field(default_factory=lambda: ["jpn"])
    # Remove the subtitles already inside the episode (except keep_sub_langs).
    # False = keep every original subtitle and just add the new one.
    remove_existing_subs: bool = True
    keep_sub_langs: list[str] = field(default_factory=list)
    edit_target_lang: str = ""
    edit_new_lang: str = "ara"
    edit_new_name: str = "Arabic"
    isolate_edited_track: bool = False
    # Shift the added subtitle: positive = show later (delay), negative = show earlier.
    subtitle_offset_ms: int = 0
    # "auto" detects (UTF-8 / Windows-1256 / ...), or an explicit charset such as "cp1256".
    subtitle_charset: str = "auto"


@dataclass
class ProcessingResult:
    """Result of processing a single episode."""
    status: ProcessingStatus = ProcessingStatus.PENDING
    output_path: Optional[Path] = None
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def is_success(self) -> bool:
        return self.status in (ProcessingStatus.COMPLETED, ProcessingStatus.COMPLETED_WITH_WARNINGS)


@dataclass
class BatchResult:
    """Aggregate results for a batch processing run."""
    total: int = 0
    successful: int = 0
    failed: int = 0
    cancelled: int = 0
    skipped: int = 0
    results: list[ProcessingResult] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    @property
    def succeeded(self) -> int:
        return self.successful


# ──────────────────────────────────────────────────────────────
# Scan & Preview
# ──────────────────────────────────────────────────────────────

@dataclass
class ScanResult:
    """Result of scanning a folder and matching files."""
    folder_path: Path = None
    series_name: str = ""
    video_files: list[EpisodeInfo] = field(default_factory=list)
    subtitle_files: list[EpisodeInfo] = field(default_factory=list)
    matches: list[EpisodeMatch] = field(default_factory=list)
    unmatched_videos: list[EpisodeInfo] = field(default_factory=list)
    unmatched_subtitles: list[EpisodeInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class PreviewOperation:
    """A single operation that will be performed."""
    action: str = ""
    target: str = ""
    description: str = ""
    icon: str = "✓"


@dataclass
class EpisodePreview:
    """Preview of what will happen to a single episode."""
    episode_num: str = ""
    video_name: str = ""
    subtitle_name: Optional[str] = None
    output_path: Optional[Path] = None
    operations: list[PreviewOperation] = field(default_factory=list)
    estimated_time_seconds: float = 0.0


@dataclass
class PreviewData:
    """Complete preview data for the batch."""
    episodes: list[EpisodePreview] = field(default_factory=list)
    operations: list[PreviewOperation] = field(default_factory=list)
    total_operations: int = 0
    estimated_total_time_seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────
# Application Configuration
# ──────────────────────────────────────────────────────────────

@dataclass
class AppConfig:
    """Persistent application configuration."""
    mkvtoolnix_path: str = r"C:\Program Files\MKVToolNix"
    last_folder: str = ""
    last_series_name: str = ""
    default_workers: int = 4
    max_concurrent_tasks: int = 4
    create_backup: bool = True
    output_subfolder: str = "PROCESSED"
    subtitle_language: str = "ara"
    subtitle_name: str = "Arabic"
    theme: str = "dark"
    window_width: int = 1100
    window_height: int = 750
    window_x: int = -1
    window_y: int = -1
    auto_detect_series_name: bool = True
    show_preview: bool = True
    remember_settings: bool = True
    watch_folder_enabled: bool = False
    presets: dict[str, dict] = field(default_factory=dict)
