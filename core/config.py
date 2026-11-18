"""
Anime Subtitle Automation Tool v2.0 — Configuration Manager

Loads and saves the persistent configuration (JSON in the user's home directory).
Everything read from disk is validated: a damaged or hand-edited file can cost
the user a setting, never the ability to start the app.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any

from core.constants import (
    CONFIG_DIR_NAME, CONFIG_FILE_NAME, MAX_PARALLEL_WORKERS, MIN_PARALLEL_WORKERS,
)
from core.models import AppConfig
from utils.logger import get_logger

logger = get_logger(__name__)

_MAX_OFFSET_MS = 3_600_000
_INVALID_FOLDER_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _get_config_dir() -> Path:
    return Path.home() / CONFIG_DIR_NAME


def _get_config_file() -> Path:
    return _get_config_dir() / CONFIG_FILE_NAME


# ── value validators: return the clean value, or None when unusable ──────────

def _as_bool(value: Any):
    return value if isinstance(value, bool) else None


def _as_str(value: Any):
    return value if isinstance(value, str) else None


def _as_workers(value: Any):
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return max(MIN_PARALLEL_WORKERS, min(MAX_PARALLEL_WORKERS, value))


def _as_offset_ms(value: Any):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or abs(value) > _MAX_OFFSET_MS:      # NaN or absurd
        return None
    return int(round(value))


def _as_lang_list(value: Any):
    # A bare string must not be accepted: list("jpn") would become ['j', 'p', 'n'].
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        return None
    return [v.strip() for v in value if v.strip()]


def valid_subfolder_name(value: Any) -> bool:
    """A plain folder name: no path separators, no '..', nothing Windows rejects."""
    if not isinstance(value, str):
        return False
    name = value.strip()
    return bool(name) and name not in (".", "..") and not _INVALID_FOLDER_CHARS.search(name) \
        and not name.endswith(".")


def _as_subfolder(value: Any):
    return value.strip() if valid_subfolder_name(value) else None


PRESET_FIELDS = {
    "keep_audio_langs": _as_lang_list,
    "keep_sub_langs": _as_lang_list,
    "remove_existing_subs": _as_bool,
    "edit_target_lang": _as_str,
    "edit_new_lang": _as_str,
    "edit_new_name": _as_str,
    "isolate_edited_track": _as_bool,
    "create_output_folder": _as_bool,
    "overwrite_existing": _as_bool,
    "process_unmatched": _as_bool,
    "dry_run": _as_bool,
    "workers": _as_workers,
    "subtitle_offset_ms": _as_offset_ms,
    "subtitle_charset": _as_str,
    "subtitle_language": _as_str,
    "subtitle_name": _as_str,
}


def clean_preset(raw: Any) -> dict:
    """Keep only known preset keys whose value has the right type.

    Unknown keys (from older versions) and wrong-typed values are dropped, so the
    caller falls back to its default for them.
    """
    if not isinstance(raw, dict):
        return {}
    clean = {}
    for key, validate in PRESET_FIELDS.items():
        if key in raw:
            value = validate(raw[key])
            if value is not None:
                clean[key] = value
    return clean


# The preset list always starts with this built-in entry; no saved preset may use it.
DEFAULT_PRESET_NAME = "Default"


def is_reserved_preset_name(name: str) -> bool:
    return name.strip().casefold() == DEFAULT_PRESET_NAME.casefold()


def _clean_presets(value: Any):
    if not isinstance(value, dict):
        return None
    presets = {}
    for name, preset in value.items():
        if not (isinstance(name, str) and name.strip() and isinstance(preset, dict)):
            continue
        name = name.strip()
        if is_reserved_preset_name(name):
            # A preset saved as 'Default' would hide behind the built-in entry
            base, n = f"{DEFAULT_PRESET_NAME} (saved)", 2
            name = base
            while name in value or name in presets:
                name, n = f"{base} {n}", n + 1
        presets[name] = clean_preset(preset)
    return presets


# What the previous version stored as its default MKVToolNix folder. Kept in an
# old config.json it would override the bundled mkvmerge, so it reads as empty.
_OLD_DEFAULT_MKVTOOLNIX = r"c:\program files\mkvtoolnix"


def _as_mkvtoolnix_path(value: Any):
    if not isinstance(value, str):
        return None
    if value.strip().rstrip("\\/").lower() == _OLD_DEFAULT_MKVTOOLNIX:
        return ""
    return value


_CONFIG_FIELDS = {
    "mkvtoolnix_path": _as_mkvtoolnix_path,
    "default_workers": _as_workers,
    "output_subfolder": _as_subfolder,
    "subtitle_language": lambda v: v.strip() if isinstance(v, str) and v.strip() else None,
    "subtitle_name": _as_str,
    "presets": _clean_presets,
}


def load_config() -> AppConfig:
    """Load the configuration. Never raises: anything unusable falls back to its default."""
    config = AppConfig()
    config_file = _get_config_file()
    try:
        if not config_file.exists():
            return config
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:  # unreadable, not UTF-8, not JSON, ...
        logger.warning(f"Could not load config ({e}); using defaults.")
        return config

    if not isinstance(data, dict):
        logger.warning("Config file does not contain a JSON object; using defaults.")
        return config

    for key, validate in _CONFIG_FIELDS.items():
        if key not in data:
            continue
        value = validate(data[key])
        if value is None:
            logger.warning(f"Ignoring invalid config value for '{key}'.")
            continue
        setattr(config, key, value)
    return config


def save_config(config: AppConfig) -> bool:
    """Save the configuration. Returns True on success."""
    config_file = _get_config_file()
    try:
        config_file.parent.mkdir(parents=True, exist_ok=True)
        data = dataclasses.asdict(config)
        # Write to a temp file first so a crash mid-write cannot leave a truncated config
        tmp = config_file.with_name(config_file.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp.replace(config_file)
        return True
    except (OSError, TypeError, ValueError) as e:
        logger.warning(f"Could not save config ({e}).")
        return False
