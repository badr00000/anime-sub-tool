"""
Click-based CLI for Anime Subtitle Automation Tool v2.0.

Provides commands: process, preview, scan, version
"""

import click
import sys
import os
import time
from pathlib import Path

# Force UTF-8 output on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

from core.models import ProcessingOptions, ProcessingStatus
from core.constants import APP_NAME, APP_VERSION, DEFAULT_PARALLEL_WORKERS
from core.engine import ProcessingEngine
from utils.logger import setup_logger, get_logger
from utils.validators import validate_folder_path, validate_series_name, validate_mkvtoolnix

import logging

logger = get_logger(__name__)


def safe_echo(text: str, **kwargs):
    """click.echo wrapper that handles Unicode safely on Windows."""
    try:
        click.echo(text, **kwargs)
    except UnicodeEncodeError:
        # Strip non-ASCII characters as fallback
        safe_text = text.encode('ascii', errors='replace').decode('ascii')
        click.echo(safe_text, **kwargs)


@click.group()
def cli():
    """Anime Subtitle Automation Tool v2.0"""
    setup_logger(level=logging.INFO)


@cli.command()
def version():
    """Show the application version."""
    safe_echo(f"{APP_NAME} v{APP_VERSION}")


@cli.command()
@click.argument('folder', type=click.Path(exists=True, file_okay=False, dir_okay=True))
def scan(folder):
    """Scan folder and show matched files."""
    try:
        folder_path = validate_folder_path(folder)
        engine = ProcessingEngine()

        safe_echo(f"Scanning: {click.style(str(folder_path), fg='cyan')}")
        result = engine.scan_and_match(str(folder_path))

        if not result.matches:
            safe_echo(click.style("[!] No matches found.", fg='yellow'))
            return

        safe_echo(click.style(f"\n[OK] Found {len(result.matches)} matched episodes:", fg='green'))
        if result.series_name:
            safe_echo(f"  Series: {click.style(result.series_name, fg='cyan')}")
        safe_echo("")

        # Table header
        safe_echo(f"  {'Ep':<6} {'Video File':<40} {'Subtitle File':<40} {'Score'}")
        safe_echo(f"  {'---':<6} {'---':<40} {'---':<40} {'---'}")

        for match in result.matches:
            ep = match.video.episode_num or "?"
            vid = match.video.filename[:37] + "..." if len(match.video.filename) > 40 else match.video.filename
            sub = (match.subtitle.filename[:37] + "...") if match.subtitle and len(match.subtitle.filename) > 40 else (match.subtitle.filename if match.subtitle else "-- None --")
            score = f"{match.score:.0f}%"

            score_color = 'green' if match.score >= 80 else ('yellow' if match.score >= 50 else 'red')
            safe_echo(f"  {ep:<6} {vid:<40} {sub:<40} {click.style(score, fg=score_color)}")

        if result.unmatched_videos:
            safe_echo(f"\n  {click.style(f'[!] {len(result.unmatched_videos)} unmatched video(s)', fg='yellow')}")
        if result.unmatched_subtitles:
            safe_echo(f"  {click.style(f'[!] {len(result.unmatched_subtitles)} unmatched subtitle(s)', fg='yellow')}")

    except Exception as e:
        safe_echo(click.style(f"[ERROR] {e}", fg='red'))
        sys.exit(1)


@cli.command()
@click.argument('folder', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--name', required=True, help='Series name')
def preview(folder, name):
    """Preview what would happen without making changes."""
    try:
        folder_path = validate_folder_path(folder)
        series_name = validate_series_name(name)

        engine = ProcessingEngine()
        safe_echo(f"Scanning: {click.style(str(folder_path), fg='cyan')}")

        scan_result = engine.scan_and_match(str(folder_path), series_name)

        if not scan_result.matches:
            safe_echo(click.style("[!] No matches found.", fg='yellow'))
            return

        opts = ProcessingOptions(series_name=series_name)
        preview_data = engine.generate_preview(scan_result, opts)

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
@click.option('--name', required=True, help='Series name')
@click.option('--workers', default=DEFAULT_PARALLEL_WORKERS, type=int, help='Number of parallel workers')
@click.option('--no-backup', is_flag=True, help='Disable original file backup')
@click.option('--output', type=click.Path(file_okay=False, dir_okay=True), help='Output directory')
@click.option('--dry-run', is_flag=True, help='Simulate without making changes')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation prompt')
@click.option('--offset', default=0.0, type=float, show_default=True,
              help='Shift the new subtitle in seconds: positive = later (delay), negative = earlier')
@click.option('--sub-charset', default='auto', show_default=True,
              help="Subtitle encoding: 'auto', 'utf-8', 'cp1256' (Arabic), or any iconv name")
def process(folder, name, workers, no_backup, output, dry_run, yes, offset, sub_charset):
    """Process a folder -- embed subtitles and filter audio tracks."""
    try:
        folder_path = validate_folder_path(folder)
        series_name = validate_series_name(name)
        validate_mkvtoolnix()

        opts = ProcessingOptions(
            series_name=series_name,
            parallel_workers=workers,
            workers=workers,
            backup_originals=not no_backup,
            create_backup=not no_backup,
            output_dir=Path(output) if output else None,
            dry_run=dry_run,
            subtitle_offset_ms=round(offset * 1000),
            subtitle_charset=sub_charset,
        )

        engine = ProcessingEngine()

        safe_echo(f"Scanning: {click.style(str(folder_path), fg='cyan')}")
        scan_result = engine.scan_and_match(str(folder_path), series_name)

        if not scan_result.matches:
            safe_echo(click.style("[!] No matches found.", fg='yellow'))
            return

        match_count = len(scan_result.matches)
        safe_echo(f"[OK] Found {click.style(str(match_count), fg='green')} episodes to process.")

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

        def progress_cb(episode_num, file_progress, overall_progress):
            pass  # Progress shown via log messages

        batch_result = engine.process_batch(scan_result, opts, progress_cb, log_cb)

        elapsed = time.time() - start_time

        # Summary
        safe_echo("")
        safe_echo(click.style("=" * 50, fg='white'))
        safe_echo(click.style("  Processing Complete!", fg='green', bold=True))
        safe_echo(click.style("=" * 50, fg='white'))
        safe_echo(f"  Total:     {batch_result.total}")
        safe_echo(f"  Succeeded: {click.style(str(batch_result.successful), fg='green')}")
        safe_echo(f"  Failed:    {click.style(str(batch_result.failed), fg='red' if batch_result.failed > 0 else 'green')}")
        safe_echo(f"  Time:      {elapsed:.1f}s")
        if elapsed > 0 and batch_result.successful > 0:
            speed = (batch_result.successful / elapsed) * 60
            safe_echo(f"  Speed:     {speed:.1f} episodes/min")

    except Exception as e:
        safe_echo(click.style(f"\n[ERROR] {e}", fg='red'))
        sys.exit(1)


@cli.command()
@click.argument('subtitle', type=click.Path(exists=True, dir_okay=False))
@click.option('--offset', required=True, type=float,
              help='Seconds: positive = show later (delay), negative = show earlier')
@click.option('--output', '-o', type=click.Path(dir_okay=False),
              help="Output file (default: '<name>.synced.<ext>' next to the original)")
def shift(subtitle, offset, output):
    """Shift every line of a .srt/.ass subtitle and save a synced copy."""
    from core import subtitle_file as sf
    try:
        sub = sf.load(subtitle)
        offset_ms = round(offset * 1000)
        out = sf.save_shifted(sub, offset_ms, output)
        safe_echo(f"[OK] {len(sub.cues)} lines shifted {sf.format_offset(offset_ms)} -> "
                  f"{click.style(str(out), fg='cyan')}")
    except (OSError, ValueError) as e:
        safe_echo(click.style(f"[ERROR] {e}", fg='red'))
        sys.exit(1)


if __name__ == '__main__':
    cli()
