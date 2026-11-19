"""
Anime Subtitle Automation Tool v2.0 — Data Models

Unified data structures used by core engine, GUI, and CLI layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional

from core.constants import DEFAULT_OUTPUT_SUBFOLDER, DEFAULT_PARALLEL_WORKERS


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
    """Metadata from mkvmerge -J. `error` is set when the file could not be read;
    `cancelled` when mkvmerge was stopped (or never started) because of a cancel."""
    filepath: Path
    tracks: list[Track] = field(default_factory=list)
    error: str = ""
    cancelled: bool = False


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
    # Season stated in the name ("S02E05", "2nd Season"); None when the name has none.
    season: Optional[int] = None
    # "" for a normal episode; otherwise the kind of extra ("NCOP", "PV", "OVA", ...).
    extra_kind: str = ""
    # Text subtitles only: human-readable detected encoding, filled in by the scan.
    encoding: str = ""
    # Release version: 2 for 'Show - 01v2', else 1.
    version: int = 1

    @property
    def label(self) -> str:
        """How the episode is named in tables and logs: '5', 'NCOP 1', 'ED', '?'."""
        if self.extra_kind:
            return f"{self.extra_kind} {self.episode_num}" if self.episode_num else self.extra_kind
        return self.episode_num or "?"


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
    # Explicit output directory (CLI --output). None = decided by the two fields below.
    output_dir: Optional[Path] = None
    create_output_folder: bool = True
    output_folder: str = DEFAULT_OUTPUT_SUBFOLDER
    # False = an episode whose output file already exists is skipped.
    overwrite_existing: bool = False
    # False = episodes without a matching subtitle are skipped (processing them
    # would only strip tracks from the episode).
    process_unmatched: bool = False
    subtitle_language: str = "ara"
    subtitle_name: str = "Arabic"
    set_default: bool = True
    parallel_workers: int = DEFAULT_PARALLEL_WORKERS
    dry_run: bool = False
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

    @classmethod
    def from_config(cls, config: "AppConfig") -> "ProcessingOptions":
        """Options carrying the defaults the user saved in Settings."""
        return cls(
            output_folder=config.output_subfolder,
            parallel_workers=config.default_workers,
            subtitle_language=config.subtitle_language,
            subtitle_name=config.subtitle_name,
        )


@dataclass
class ProcessingResult:
    """Result of processing a single episode."""
    status: ProcessingStatus = ProcessingStatus.PENDING
    output_path: Optional[Path] = None
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    video_name: str = ""

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
    dry_run: bool = False
    results: list[ProcessingResult] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────
# Scan & Preview
# ──────────────────────────────────────────────────────────────

@dataclass
class ScanResult:
    """Result of scanning a folder and matching files."""
    folder_path: Optional[Path] = None
    video_files: list[EpisodeInfo] = field(default_factory=list)
    subtitle_files: list[EpisodeInfo] = field(default_factory=list)
    matches: list[EpisodeMatch] = field(default_factory=list)
    unmatched_videos: list[EpisodeInfo] = field(default_factory=list)
    unmatched_subtitles: list[EpisodeInfo] = field(default_factory=list)


@dataclass
class PreviewOperation:
    """A single operation that will be performed."""
    action: str = ""
    target: str = ""


@dataclass
class EpisodePreview:
    """Preview of what will happen to a single episode."""
    episode_num: str = ""
    video_name: str = ""
    subtitle_name: Optional[str] = None
    output_path: Optional[Path] = None
    operations: list[PreviewOperation] = field(default_factory=list)


@dataclass
class PreviewData:
    """Complete preview data for the batch."""
    episodes: list[EpisodePreview] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────
# Application Configuration
# ──────────────────────────────────────────────────────────────

@dataclass
class AppConfig:
    """Persistent application configuration (Settings dialog + presets)."""
    # Folder of a system MKVToolNix to use instead; empty = the bundled mkvmerge.
    mkvtoolnix_path: str = ""
    default_workers: int = DEFAULT_PARALLEL_WORKERS
    output_subfolder: str = DEFAULT_OUTPUT_SUBFOLDER
    subtitle_language: str = "ara"
    subtitle_name: str = "Arabic"
    presets: dict[str, dict] = field(default_factory=dict)
