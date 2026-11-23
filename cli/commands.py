"""
Click-based CLI for Anime Subtitle Automation Tool.

Provides commands: process, preview, scan, shift, version
"""

import click
import math
import sys
import os
import time
from pathlib import Path

# Force UTF-8 output on Windows. A windowed .exe has no console: its streams are None.
if sys.platform == 'win32':
    for _stream in (sys.stdout, sys.stderr):
        if _stream is not None and hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding='utf-8', errors='replace')
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

from core.config import _MAX_OFFSET_MS, load_config
from core.models import MatchConfidence, ProcessingOptions
from core.constants import (
    APP_NAME, APP_VERSION, MAX_PARALLEL_WORKERS, MIN_PARALLEL_WORKERS,
)
from core.engine import ProcessingEngine
from utils.logger import setup_logging
from utils.validators import validate_folder_path, validate_mkvtoolnix


def safe_echo(text: str, **kwargs):
    """click.echo wrapper that handles Unicode safely on Windows."""
    try:
        click.echo(text, **kwargs)
    except UnicodeEncodeError:
        # Strip non-ASCII characters as fallback
        safe_text = text.encode('ascii', errors='replace').decode('ascii')
        click.echo(safe_text, **kwargs)


def _clip(name: str, width: int = 40) -> str:
    return name[:width - 3] + "..." if len(name) > width else name


@click.group()
def cli():
    """Anime Subtitle Automation Tool"""
    setup_logging(console=True)


@cli.command()
def version():
    """Show the application version."""
    safe_echo(f"{APP_NAME} v{APP_VERSION}")


def _match_warnings(match) -> list[str]:
    """Why a pair needs a look: an unrelated-looking title (LOW confidence),
    another language in the name, a season only assumed, a partial track."""
    warnings = []
    if match.subtitle is not None and match.confidence == MatchConfidence.LOW:
        warnings.append(f"the titles look different (title match {match.score:.0f}%); "
                        "make sure the subtitle is for this show")
    return warnings + [text for text in (match.language_warning, match.note) if text]


def _echo_pairs_to_check(matches) -> None:
    """List the pairs that need a look (used before `preview` and `process`)."""
    flagged = [(m, _match_warnings(m)) for m in matches if m.subtitle and _match_warnings(m)]
    if not flagged:
        return
    safe_echo(click.style(f"\n[!] {len(flagged)} pair(s) to check:", fg='yellow'))
    for match, warnings in flagged:
        safe_echo(f"  Episode {match.video.label}: {match.video.filename}  <-  {match.subtitle.filename}")
        for text in warnings:
            safe_echo(click.style(f"         [!] Check: {text}", fg='yellow'))


@cli.command()
@click.argument('folder', type=click.Path(exists=True, file_okay=False, dir_okay=True))
def scan(folder):
    """Scan folder and show matched files."""
    try:
        folder_path = validate_folder_path(folder)
        engine = ProcessingEngine(load_config())

        safe_echo(f"Scanning: {click.style(str(folder_path), fg='cyan')}")
        result = engine.scan_and_match(folder_path)

        if not result.matches:
            safe_echo(click.style("[!] No episodes found.", fg='yellow'))
            return

        matched = sum(1 for m in result.matches if m.is_matched)
        safe_echo(click.style(f"\n[OK] {len(result.matches)} episode(s), {matched} with a subtitle:", fg='green'))
        safe_echo("")

        # Table header
        safe_echo(f"  {'Ep':<6} {'Video File':<40} {'Subtitle File':<40} {'Title match'}")
        safe_echo(f"  {'---':<6} {'---':<40} {'---':<40} {'---'}")

        for match in result.matches:
            ep = match.video.label
            vid = _clip(match.video.filename)
            sub = _clip(match.subtitle.filename) if match.subtitle else "-- None --"
            if match.subtitle:
                score = f"{match.score:.0f}% ({match.confidence.name})"
                score_color = 'green' if match.score >= 80 else ('yellow' if match.score >= 50 else 'red')
            else:
                score, score_color = "-", 'red'
            safe_echo(f"  {ep:<6} {vid:<40} {sub:<40} {click.style(score, fg=score_color)}")
            for text in _match_warnings(match) if match.subtitle else ():
                safe_echo(click.style(f"         [!] Check: {text}", fg='yellow'))

        if result.unmatched_videos:
            safe_echo(f"\n  {click.style(f'[!] {len(result.unmatched_videos)} unmatched video(s)', fg='yellow')}")
        if result.unmatched_subtitles:
            safe_echo(f"  {click.style(f'[!] {len(result.unmatched_subtitles)} unmatched subtitle(s)', fg='yellow')}")
        _echo_pairs_to_check(result.matches)

    except Exception as e:
        safe_echo(click.style(f"[ERROR] {e}", fg='red'))
        sys.exit(1)


# Same limit the configuration accepts for a saved offset
_MAX_OFFSET_SECONDS = _MAX_OFFSET_MS // 1000


def _check_offset(ctx, param, value):
    """Reject offsets that are not a real number of seconds within one hour."""
    if value is None:
        return value
    if not math.isfinite(value) or abs(value) > _MAX_OFFSET_SECONDS:
        raise click.BadParameter(
            f"must be a number of seconds between -{_MAX_OFFSET_SECONDS} and {_MAX_OFFSET_SECONDS}.")
    return value


def _check_charset(ctx, param, value):
    """Only encodings from the table mkvmerge is known to accept get through."""
    from core.subtitles import is_known_charset
    if not is_known_charset(value):
        raise click.BadParameter(f"unknown encoding '{value}'.")
    return value


_LANG_CODE = __import__("re").compile(r"^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*$")


def _check_languages(ctx, param, value):
    """'jpn,en, ja-JP' -> ['jpn', 'eng', 'jpn']; '' or 'all' -> [] (no filter).
    None (option not given) keeps the default."""
    from core.languages import normalize
    if value is None:
        return None
    if value.strip().lower() in ("", "all"):
        return []
    codes = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if not _LANG_CODE.match(item):
            raise click.BadParameter(f"'{item}' is not a language code (e.g. jpn, ja, eng).")
        code = normalize(item)
        if code not in codes:
            codes.append(code)
    return codes


# --keep-subs all: keep every original subtitle (the same as --keep-original-subs)
KEEP_ALL = "all"


def _check_keep_subs(ctx, param, value):
    """Like _check_languages, but 'all' means keep every original subtitle."""
    if value is not None and value.strip().lower() == KEEP_ALL:
        return KEEP_ALL
    return _check_languages(ctx, param, value)


def _processing_options(func):
    """Options shared by `preview` and `process`, so the preview shows what process will do."""
    decorators = [
        click.option('--output', type=click.Path(file_okay=False, dir_okay=True),
                     help='Folder to write the processed files to '
                          '(default: the output subfolder inside FOLDER)'),
        click.option('--offset', default=0.0, type=float, show_default=True, callback=_check_offset,
                     help='Shift the new subtitle in seconds: positive = later (delay), negative = earlier'),
        click.option('--sub-charset', default='auto', show_default=True, callback=_check_charset,
                     help="Subtitle encoding: 'auto', 'utf-8', 'cp1256' (Arabic), 'cp1252', "
                          "'cp1250', 'cp1254', 'cp1258', 'cp1251', 'koi8_r', 'cp1253', 'cp1255', 'cp874', "
                          "'shift_jis', 'gb18030', 'big5', 'euc-kr', 'utf-16' (or another name "
                          "mkvmerge knows, e.g. 'iso8859_2')"),
        click.option('--keep-audio', 'keep_audio', default=None, callback=_check_languages,
                     metavar='LANGS',
                     help="Audio languages to keep, comma separated (jpn, ja, eng, ...). "
                          "'all' or '' keeps every audio track. Default: jpn (an episode "
                          "without Japanese audio keeps all of its audio)"),
        click.option('--keep-subs', 'keep_subs', default=None, callback=_check_keep_subs,
                     metavar='LANGS',
                     help="Original subtitle languages NOT removed, comma separated "
                          "(default: none, every original subtitle is removed). "
                          "'all' keeps every original subtitle (same as "
                          "--keep-original-subs). Ignored with --keep-original-subs"),
        click.option('--keep-original-subs', is_flag=True,
                     help='Keep the subtitles already inside each episode (default: remove them)'),
        click.option('--overwrite', is_flag=True,
                     help='Replace output files that already exist (default: skip those episodes)'),
        click.option('--include-unmatched', is_flag=True,
                     help='Also process episodes that have no matching subtitle (default: skip them)'),
    ]
    for decorator in reversed(decorators):
        func = decorator(func)
    return func


def _build_options(config, output, offset, sub_charset, keep_original_subs, overwrite,
                   include_unmatched, keep_audio=None, keep_subs=None, **extra) -> ProcessingOptions:
    opts = ProcessingOptions.from_config(config)
    if keep_audio is not None:
        opts.keep_audio_langs = keep_audio
    if keep_subs == KEEP_ALL:
        keep_original_subs = True
        opts.keep_sub_langs = []
    elif keep_subs is not None:
        opts.keep_sub_langs = keep_subs
    opts.output_dir = Path(output).resolve() if output else None
    opts.subtitle_offset_ms = round(offset * 1000)
    opts.subtitle_charset = sub_charset
    opts.remove_existing_subs = not keep_original_subs
    opts.overwrite_existing = overwrite
    opts.process_unmatched = include_unmatched
    for key, value in extra.items():
        setattr(opts, key, value)
    return opts


@cli.command()
@click.argument('folder', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@_processing_options
def preview(folder, output, offset, sub_charset, keep_audio, keep_subs, keep_original_subs,
            overwrite, include_unmatched):
    """Preview what would happen without making changes."""
    try:
        folder_path = validate_folder_path(folder)
        config = load_config()
        engine = ProcessingEngine(config)
        safe_echo(f"Scanning: {click.style(str(folder_path), fg='cyan')}")

        scan_result = engine.scan_and_match(folder_path)

        if not scan_result.matches:
            safe_echo(click.style("[!] No episodes found.", fg='yellow'))
            return

        opts = _build_options(config, output, offset, sub_charset, keep_original_subs,
                              overwrite, include_unmatched, keep_audio, keep_subs)
        preview_data = engine.generate_preview(scan_result, opts)
        _echo_pairs_to_check(scan_result.matches)

        safe_echo(click.style(f"\n[OK] Preview -- {len(preview_data.episodes)} episodes:", fg='green'))
        safe_echo("")

        for ep in preview_data.episodes:
            safe_echo(f"  Episode {click.style(ep.episode_num, fg='cyan')}:")
            safe_echo(f"    Video:    {ep.video_name}")
            if ep.subtitle_name:
                safe_echo(f"    Subtitle: {ep.subtitle_name}")
            for op in ep.operations:
                safe_echo(f"    > {op.action}: {op.target}")
            safe_echo("")

    except Exception as e:
        safe_echo(click.style(f"[ERROR] {e}", fg='red'))
        sys.exit(1)


@cli.command()
@click.argument('folder', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--workers', default=None,
              type=click.IntRange(MIN_PARALLEL_WORKERS, MAX_PARALLEL_WORKERS),
              help=f'Episodes processed at once ({MIN_PARALLEL_WORKERS}-{MAX_PARALLEL_WORKERS}; '
                   'default: the value saved in Settings)')
@click.option('--dry-run', is_flag=True, help='Simulate without making changes')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation prompt')
@_processing_options
def process(folder, workers, dry_run, yes, output, offset, sub_charset, keep_audio, keep_subs,
            keep_original_subs, overwrite, include_unmatched):
    """Process a folder -- embed subtitles and filter audio tracks.

    By default only Japanese audio is kept (all audio when an episode has no
    Japanese track) and every original subtitle is removed; see --keep-audio,
    --keep-subs and --keep-original-subs.
    """
    try:
        folder_path = validate_folder_path(folder)
        config = load_config()
        engine = ProcessingEngine(config)
        validate_mkvtoolnix(engine.mkv_tools)

        opts = _build_options(config, output, offset, sub_charset, keep_original_subs,
                              overwrite, include_unmatched, keep_audio, keep_subs, dry_run=dry_run)
        if workers is not None:
            opts.parallel_workers = workers

        safe_echo(f"Scanning: {click.style(str(folder_path), fg='cyan')}")
        scan_result = engine.scan_and_match(folder_path)

        if not scan_result.matches:
            safe_echo(click.style("[!] No episodes found.", fg='yellow'))
            return

        match_count = len(scan_result.matches)
        matched = sum(1 for m in scan_result.matches if m.is_matched)
        safe_echo(f"[OK] Found {click.style(str(match_count), fg='green')} episode(s), "
                  f"{matched} with a matching subtitle.")
        safe_echo(f"  Output folder: {engine.output_dir(scan_result, opts)}")
        _echo_pairs_to_check(scan_result.matches)

        if dry_run:
            safe_echo(click.style("  [DRY RUN MODE -- no changes will be made]", fg='yellow'))

        if not yes:
            if not click.confirm("\nProceed with processing?"):
                safe_echo("Cancelled.")
                return

        safe_echo("")

        start_time = time.time()

        def log_cb(msg, level="INFO"):
            if level == "ERROR":
                safe_echo(click.style(f"  [X] {msg}", fg='red'))
            elif level == "WARNING":
                safe_echo(click.style(f"  [!] {msg}", fg='yellow'))
            else:
                safe_echo(click.style(f"  [+] {msg}", fg='green'))

        batch_result = engine.process_batch(scan_result, opts, None, log_cb)

        elapsed = time.time() - start_time

        # Summary
        safe_echo("")
        safe_echo(click.style("=" * 50, fg='white'))
        title = "Dry run finished -- nothing was written" if dry_run else "Processing finished"
        safe_echo(click.style(f"  {title}", fg='green', bold=True))
        safe_echo(click.style("=" * 50, fg='white'))
        safe_echo(f"  Total:     {batch_result.total}")
        done_label = "Would do: " if dry_run else "Succeeded:"
        safe_echo(f"  {done_label} {click.style(str(batch_result.successful), fg='green')}")
        safe_echo(f"  Skipped:   {click.style(str(batch_result.skipped), fg='yellow' if batch_result.skipped else 'green')}")
        safe_echo(f"  Failed:    {click.style(str(batch_result.failed), fg='red' if batch_result.failed > 0 else 'green')}")
        safe_echo(f"  Time:      {elapsed:.1f}s")

        if batch_result.failed:
            sys.exit(1)

    except KeyboardInterrupt:
        # The batch already stopped mkvmerge and removed unfinished files
        safe_echo(click.style("\nCancelled.", fg='yellow'))
        sys.exit(130)
    except Exception as e:
        safe_echo(click.style(f"\n[ERROR] {e}", fg='red'))
        sys.exit(1)


@cli.command()
@click.argument('subtitle', type=click.Path(exists=True, dir_okay=False))
@click.option('--offset', required=True, type=float, callback=_check_offset,
              help='Seconds: positive = show later (delay), negative = show earlier')
@click.option('--output', '-o', type=click.Path(dir_okay=False),
              help="Output file (default: '<name>.synced.<ext>' next to the original)")
@click.option('--force', is_flag=True,
              help='Allow writing over the subtitle file that was read')
def shift(subtitle, offset, output, force):
    """Shift every line of a .srt/.ass subtitle and save a synced copy."""
    from core import subtitle_file as sf
    try:
        sub = sf.load(Path(subtitle).resolve())
        if not sub.cues:
            raise ValueError(f"'{sub.path.name}' contains no subtitle lines; nothing to shift.")
        offset_ms = round(offset * 1000)
        if sf.all_cues_gone(sub, offset_ms):
            raise ValueError(f"A {sf.format_offset(offset_ms)} shift moves every line of "
                             f"'{sub.path.name}' to or before 0:00; nothing would be left. "
                             "Use a smaller offset.")
        clamped = sf.count_clamped(sub, offset_ms)
        out = sf.save_shifted(sub, offset_ms, Path(output).resolve() if output else None, force=force)
        if clamped:
            safe_echo(click.style(
                f"[!] Warning: {clamped} of {len(sub.cues)} line(s) would start before 0:00 "
                "and were moved to 0:00.", fg='yellow'))
        safe_echo(f"[OK] {len(sub.cues)} lines shifted {sf.format_offset(offset_ms)} -> "
                  f"{click.style(str(out), fg='cyan')}")
    except sf.SameFileError as e:
        safe_echo(click.style(f"[ERROR] {e} Use --force to overwrite it, or -o to pick another file.", fg='red'))
        sys.exit(1)
    except (OSError, ValueError) as e:
        safe_echo(click.style(f"[ERROR] {e}", fg='red'))
        sys.exit(1)


if __name__ == '__main__':
    cli()
