import os
from pathlib import Path
from typing import Callable, Iterable, Optional

from core import subtitle_file
from core.constants import TEXT_SUBTITLE_EXTENSIONS
from core.languages import normalize, same_language
from core.mkvtools import MKVToolsWrapper
from core.models import (
    EpisodeMatch, EpisodePreview, PreviewOperation, ProcessingOptions, ProcessingResult,
    ProcessingStatus, TrackType,
)
from core.subtitles import CHARSET_AUTO, python_codec, resolve_charset
from utils.logger import get_logger
from utils.paths import output_filename, resolve_output_dir

logger = get_logger(__name__)

# mkvmerge writes here first; the file only gets its real name once it is complete,
# so a failed or interrupted run never leaves something that looks like a finished episode.
_PARTIAL_SUFFIX = ".partial"


def _same_path(a: Path, b: Path) -> bool:
    return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))


class EpisodeProcessor:
    def __init__(self, mkv_tools: MKVToolsWrapper, options: ProcessingOptions,
                 protected_paths: Optional[Iterable[Path]] = None):
        self.mkv_tools = mkv_tools
        self.options = options
        self.protected_paths: set[str] = set()
        self.protect(protected_paths or ())

    def protect(self, paths: Iterable[Path]) -> None:
        """Register input files of the batch: no output may ever be written onto them."""
        for path in paths:
            self.protected_paths.add(os.path.normcase(str(Path(path).resolve())))

    def output_dir(self, video_path: Path) -> Path:
        return resolve_output_dir(video_path.parent, self.options.output_dir,
                                  self.options.create_output_folder, self.options.output_folder)

    def output_path(self, video_path: Path) -> Path:
        """Where the processed file goes. Pure computation: creates nothing on disk."""
        output_dir = self.output_dir(video_path)
        same_folder = _same_path(output_dir, video_path.parent)
        return output_dir / output_filename(video_path.name, same_folder)

    # ── checks shared by the real run, the dry run and the preview ──

    def _precheck(self, match: EpisodeMatch) -> Optional[ProcessingResult]:
        """A SKIPPED/FAILED result when this episode must not be processed, else None."""
        if not match.video or not match.video.filepath:
            return ProcessingResult(status=ProcessingStatus.FAILED, message="No video file found in match.")
        video_path = match.video.filepath
        output_path = self.output_path(video_path)

        if match.subtitle is None and not self.options.process_unmatched:
            return ProcessingResult(status=ProcessingStatus.SKIPPED, output_path=output_path,
                                    message=f"No matching subtitle for {video_path.name}")

        inputs = set(self.protected_paths)
        inputs.add(os.path.normcase(str(video_path.resolve())))
        if match.subtitle:
            inputs.add(os.path.normcase(str(match.subtitle.filepath.resolve())))
        if os.path.normcase(str(output_path.resolve())) in inputs:
            return ProcessingResult(
                status=ProcessingStatus.FAILED, output_path=output_path,
                message=f"Refusing to write {output_path.name}: it is one of the input files.")

        if output_path.exists() and not self.options.overwrite_existing:
            return ProcessingResult(
                status=ProcessingStatus.SKIPPED, output_path=output_path,
                message=f"Output already exists: {output_path.name} "
                        "(enable 'Overwrite existing output files' to replace it)")
        return None

    def _inspect_subtitle(self, sub_path: Path) -> tuple[Optional[str], list[str]]:
        """(error, warnings) for the subtitle about to be merged."""
        if sub_path.suffix.lower() not in TEXT_SUBTITLE_EXTENSIONS:
            return None, []
        try:
            sub = subtitle_file.load(sub_path)
        except OSError as e:
            return f"Could not read subtitle {sub_path.name}: {e}", []
        except ValueError as e:
            if (self.options.subtitle_charset or "").strip().lower() not in ("", CHARSET_AUTO):
                return None, []   # the user named the encoding; let mkvmerge judge the file
            return str(e), []
        if not sub.cues:
            return (f"Subtitle {sub_path.name} contains no subtitle lines "
                    "(empty or damaged file); nothing was merged."), []

        warnings = []
        clamped = subtitle_file.count_clamped(sub, self.options.subtitle_offset_ms)
        if clamped:
            warnings.append(
                f"{sub_path.name}: {clamped} of {len(sub.cues)} line(s) start before 0:00 after the "
                f"{subtitle_file.format_offset(self.options.subtitle_offset_ms)} shift and are cut or dropped.")
        return None, warnings

    # ── processing ──

    def process(self, match: EpisodeMatch, progress_callback: Optional[Callable[[int], None]] = None) -> ProcessingResult:
        blocked = self._precheck(match)
        if blocked:
            return blocked

        video_path = match.video.filepath
        output_path = self.output_path(video_path)
        sub_path = match.subtitle.filepath if match.subtitle else None

        pre_warnings: list[str] = []
        if sub_path:
            error, pre_warnings = self._inspect_subtitle(sub_path)
            if error:
                return ProcessingResult(status=ProcessingStatus.FAILED, output_path=output_path, message=error)

        # 1. Identify tracks
        file_info = self.mkv_tools.identify(str(video_path))
        if file_info.error:
            return ProcessingResult(status=ProcessingStatus.FAILED, output_path=output_path,
                                    message=file_info.error)

        # 2. Find Audio track IDs to keep
        audio_tracks = [t for t in file_info.tracks if t.type == TrackType.AUDIO]
        # None = keep every audio track. An empty filter means "no filter", never
        # "remove all audio": a video with no sound is never what the user wants here.
        audio_track_ids = None
        if self.options.keep_audio_langs:
            keep_audio = {normalize(c) for c in self.options.keep_audio_langs}
            wanted = [t.id for t in audio_tracks if normalize(t.language) in keep_audio]
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
                if same_language(t.language, self.options.edit_target_lang):
                    edited_track_id = t.id
                    break  # Only edit the first matching track

        # None = keep every original subtitle (mkvmerge default); a list = keep only those ids
        if not self.options.remove_existing_subs:
            sub_track_ids = None
        elif self.options.keep_sub_langs:
            keep_subs = {normalize(c) for c in self.options.keep_sub_langs}
            sub_track_ids = [t.id for t in sub_tracks if normalize(t.language) in keep_subs]
        else:
            sub_track_ids = []  # remove all original subtitles

        if edited_track_id is not None:
            if self.options.isolate_edited_track:
                sub_track_ids = [edited_track_id]  # clear all others
            elif sub_track_ids is not None and edited_track_id not in sub_track_ids:
                sub_track_ids.append(edited_track_id)  # ensure it's kept

        # 4. The output folder is only created now, when we really write
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return ProcessingResult(status=ProcessingStatus.FAILED, output_path=output_path,
                                    message=f"Could not create the output folder {output_path.parent}: {e}")
        partial_path = output_path.with_name(output_path.name + _PARTIAL_SUFFIX)

        # 5. Execute mkvmerge
        sub_charset = resolve_charset(sub_path, self.options.subtitle_charset) if sub_path else None
        merge_sub_path = sub_path
        temp_sub_path = None
        if sub_path and sub_charset in ("UTF-16LE", "UTF-16BE"):
            # mkvmerge cannot even recognise a UTF-16 subtitle that has no BOM, so it
            # gets a UTF-8 copy (written next to the output, removed afterwards).
            temp_sub_path = output_path.with_name(output_path.name + _PARTIAL_SUFFIX + sub_path.suffix)
            try:
                codec = python_codec("utf-16-le" if sub_charset == "UTF-16LE" else "utf-16-be")
                text = sub_path.read_bytes().decode(codec, errors="replace")
                with open(temp_sub_path, "w", encoding="utf-8-sig", newline="") as f:
                    f.write(text)
            except OSError as e:
                return ProcessingResult(status=ProcessingStatus.FAILED, output_path=output_path,
                                        message=f"Could not convert subtitle {sub_path.name}: {e}")
            merge_sub_path, sub_charset = temp_sub_path, None

        result = self.mkv_tools.merge(
            video_path=str(video_path),
            output_path=str(partial_path),
            subtitle_path=str(merge_sub_path) if merge_sub_path else None,
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

        result.output_path = output_path
        result.warnings = pre_warnings + list(result.warnings)
        try:
            if temp_sub_path is not None and temp_sub_path.exists():
                temp_sub_path.unlink()
            if result.is_success:
                if partial_path.exists():
                    os.replace(partial_path, output_path)
                else:
                    result.status = ProcessingStatus.FAILED
                    result.message = f"mkvmerge reported success but wrote no file for {video_path.name}."
            elif partial_path.exists():
                partial_path.unlink()
        except OSError as e:
            result.status = ProcessingStatus.FAILED
            result.message = f"Could not finish writing {output_path.name}: {e}"
        return result

    def dry_run(self, match: EpisodeMatch) -> ProcessingResult:
        """Simulate without writing anything. Reports the same skips and subtitle
        problems the real run would."""
        blocked = self._precheck(match)
        if blocked:
            return blocked
        output_path = self.output_path(match.video.filepath)
        warnings: list[str] = []
        if match.subtitle:
            error, warnings = self._inspect_subtitle(match.subtitle.filepath)
            if error:
                return ProcessingResult(status=ProcessingStatus.FAILED, output_path=output_path, message=error)
        return ProcessingResult(
            status=ProcessingStatus.COMPLETED,
            output_path=output_path,
            message="Dry run: nothing was written.",
            warnings=warnings,
        )

    def generate_preview(self, match: EpisodeMatch) -> EpisodePreview:
        """Generate preview data for this episode."""
        video_path = match.video.filepath

        # Same path process() will write to, without touching the disk
        output_path = self.output_path(video_path)
        preview = EpisodePreview(
            episode_num=match.video.episode_num or "?",
            video_name=video_path.name,
            subtitle_name=match.subtitle.filepath.name if match.subtitle else None,
            output_path=output_path,
        )

        blocked = self._precheck(match)
        if blocked:
            action = "Skip" if blocked.status == ProcessingStatus.SKIPPED else "Cannot process"
            preview.operations = [PreviewOperation(action=action, target=blocked.message)]
            return preview

        operations = [
            PreviewOperation(action="Merge", target=str(video_path.name)),
            PreviewOperation(action="Write", target=str(output_path)),
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

        if self.options.isolate_edited_track and self.options.edit_target_lang:
            operations.append(PreviewOperation(action="Filter Subtitles", target="Keep ONLY the edited track"))
        elif not self.options.remove_existing_subs:
            operations.append(PreviewOperation(action="Keep Subtitles", target="All existing original subtitles"))
        elif self.options.keep_sub_langs:
            operations.append(PreviewOperation(action="Remove Subtitles", target=f"All original subs except {', '.join(self.options.keep_sub_langs)}"))
        else:
            operations.append(PreviewOperation(action="Remove Subtitles", target="All existing original subs (except edited)"))

        if self.options.keep_audio_langs:
            operations.append(PreviewOperation(action="Filter Audio", target=f"Keep {', '.join(self.options.keep_audio_langs)} (if found)"))
        else:
            operations.append(PreviewOperation(action="Filter Audio", target="Keep all audio"))

        preview.operations = operations
        return preview
