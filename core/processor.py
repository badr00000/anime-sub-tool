from pathlib import Path
from typing import Callable, Optional
from core.models import EpisodeMatch, ProcessingOptions, ProcessingResult, ProcessingStatus, EpisodePreview, PreviewOperation, TrackType, Track
from core.mkvtools import MKVToolsWrapper
from core.subtitles import resolve_charset
from core.constants import JAPANESE_LANGUAGE_CODES, ARABIC_LANGUAGE_CODES
from utils.logger import get_logger
from utils.paths import generate_output_filename, ensure_output_dir

logger = get_logger(__name__)

class EpisodeProcessor:
    def __init__(self, mkv_tools: MKVToolsWrapper, options: ProcessingOptions):
        self.mkv_tools = mkv_tools
        self.options = options

    def _output_path(self, video_path: Path) -> Path:
        """Where the processed file goes. Pure computation: creates nothing on disk."""
        if self.options.create_output_folder:
            output_dir = video_path.parent / self.options.output_folder
        else:
            output_dir = video_path.parent

        output_path = output_dir / generate_output_filename(video_path.name, self.options.output_suffix)

        # Never let mkvmerge overwrite the input file
        if output_path.resolve() == video_path.resolve():
            output_path = output_dir / generate_output_filename(video_path.name, "_new")
        return output_path

    def process(self, match: EpisodeMatch, progress_callback: Optional[Callable[[int], None]] = None) -> ProcessingResult:
        if not match.video or not match.video.filepath:
            return ProcessingResult(status=ProcessingStatus.FAILED, output_path=None, message="No video file found in match.")
            
        video_path = match.video.filepath
        
        # 1. Identify tracks
        file_info = self.mkv_tools.identify(str(video_path))
        
        # 2. Find Audio track IDs to keep
        audio_tracks = [t for t in file_info.tracks if t.type == TrackType.AUDIO]
        # None = keep every audio track. An empty filter means "no filter", never
        # "remove all audio": a video with no sound is never what the user wants here.
        audio_track_ids = None
        if self.options.keep_audio_langs:
            wanted = [t.id for t in audio_tracks if t.language in self.options.keep_audio_langs]
            if wanted:
                audio_track_ids = wanted
            else:
                logger.warning(f"No specified audio langs {self.options.keep_audio_langs} found for {video_path.name}. Keeping all audio.")

        # 3. Handle subtitles
        sub_tracks = [t for t in file_info.tracks if t.type == TrackType.SUBTITLE]
        
        # Track Metadata Editor Logic
        edited_track_id = None
        if self.options.edit_target_lang:
            for t in sub_tracks:
                if t.language == self.options.edit_target_lang:
                    edited_track_id = t.id
                    break  # Only edit the first matching track
                    
        if self.options.keep_sub_langs:
            sub_track_ids = [t.id for t in sub_tracks if t.language in self.options.keep_sub_langs]
        else:
            sub_track_ids = [] # strip all original subs by default
            
        if edited_track_id is not None:
            if self.options.isolate_edited_track:
                sub_track_ids = [edited_track_id] # Clear all others
            elif edited_track_id not in sub_track_ids:
                sub_track_ids.append(edited_track_id) # Ensure it's kept

        # 4. Build Output Path (the folder is only created now, when we really write)
        output_path = self._output_path(video_path)
        if self.options.create_output_folder:
            ensure_output_dir(video_path.parent, self.options.output_folder)

        # 5. Execute mkvmerge
        subtitle_path = str(match.subtitle.filepath) if match.subtitle else None
        sub_charset = resolve_charset(match.subtitle.filepath, self.options.subtitle_charset) if match.subtitle else None

        result = self.mkv_tools.merge(
            video_path=str(video_path),
            output_path=str(output_path),
            subtitle_path=subtitle_path,
            audio_track_ids=audio_track_ids,
            sub_track_ids=sub_track_ids,
            sub_language=self.options.subtitle_language,
            sub_name=self.options.subtitle_name,
            sub_default=self.options.set_default,
            edit_track_id=edited_track_id,
            edit_new_lang=self.options.edit_new_lang,
            edit_new_name=self.options.edit_new_name,
            sub_offset_ms=self.options.subtitle_offset_ms,
            sub_charset=sub_charset,
            progress_callback=progress_callback
        )
        
        return result

    def dry_run(self, match: EpisodeMatch) -> ProcessingResult:
        """Simulate without executing. Return what would happen."""
        preview = self.generate_preview(match)
        
        return ProcessingResult(
            status=ProcessingStatus.COMPLETED,
            output_path=preview.output_path,
            message="Dry run successful."
        )

    def generate_preview(self, match: EpisodeMatch) -> EpisodePreview:
        """Generate preview data for this episode."""
        video_path = match.video.filepath

        # Same path process() will write to, without touching the disk
        output_path = self._output_path(video_path)

        operations = [
            PreviewOperation(action="Merge", target=str(video_path.name)),
        ]
        
        if match.subtitle:
            operations.append(PreviewOperation(action="Add Subtitle", target=str(match.subtitle.filepath.name)))
            operations.append(PreviewOperation(action="Set Properties", target=f"Lang: {self.options.subtitle_language}, Default: {self.options.set_default}"))
            offset = self.options.subtitle_offset_ms
            if offset:
                direction = "later (delay)" if offset > 0 else "earlier"
                operations.append(PreviewOperation(action="Shift Subtitle", target=f"{abs(offset) / 1000:g}s {direction}"))
            charset = resolve_charset(match.subtitle.filepath, self.options.subtitle_charset)
            if charset:
                operations.append(PreviewOperation(action="Convert Encoding", target=f"{charset} → UTF-8"))
            
        if self.options.edit_target_lang:
            iso_text = " (and isolating it)" if self.options.isolate_edited_track else ""
            operations.append(PreviewOperation(
                action="Edit Track", 
                target=f"Convert '{self.options.edit_target_lang}' to '{self.options.edit_new_lang}'{iso_text}"
            ))

        if self.options.keep_sub_langs and not self.options.isolate_edited_track:
            operations.append(PreviewOperation(action="Filter Subtitles", target=f"Keep {', '.join(self.options.keep_sub_langs)}"))
        elif self.options.isolate_edited_track:
            operations.append(PreviewOperation(action="Filter Subtitles", target="Keep ONLY the edited track"))
        else:
            operations.append(PreviewOperation(action="Strip Subtitles", target="All existing original subs (except edited)"))
            
        if self.options.keep_audio_langs:
            operations.append(PreviewOperation(action="Filter Audio", target=f"Keep {', '.join(self.options.keep_audio_langs)} (if found)"))
        else:
            operations.append(PreviewOperation(action="Filter Audio", target="Keep all audio"))
            
        return EpisodePreview(
            episode_num=match.video.episode_num or "?",
            video_name=video_path.name,
            subtitle_name=match.subtitle.filepath.name if match.subtitle else None,
            output_path=output_path,
            operations=operations
        )
