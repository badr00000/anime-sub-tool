"""
Anime Subtitle Automation Tool v2.0 — Configuration Manager

Handles loading, saving, and managing persistent app configuration
stored as JSON in the user's home directory.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from core.constants import CONFIG_DIR_NAME, CONFIG_FILE_NAME
from core.models import AppConfig


def _get_config_dir() -> Path:
    """Get the configuration directory path."""
    home = Path.home()
    config_dir = home / CONFIG_DIR_NAME
    return config_dir


def _get_config_file() -> Path:
    """Get the configuration file path."""
    return _get_config_dir() / CONFIG_FILE_NAME


def load_config() -> AppConfig:
    """
    Load configuration from disk.
    Returns default config if file doesn't exist or is corrupted.
    """
    config_file = _get_config_file()

    if not config_file.exists():
        return AppConfig()

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Create config from saved data, using defaults for missing keys
        config = AppConfig()
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        return config

    except (json.JSONDecodeError, OSError, TypeError) as e:
        # Corrupted config — return defaults
        print(f"Warning: Could not load config ({e}), using defaults.")
        return AppConfig()


def save_config(config: AppConfig) -> bool:
    """
    Save configuration to disk.
    Returns True on success, False on failure.
    """
    config_dir = _get_config_dir()
    config_file = _get_config_file()

    try:
        config_dir.mkdir(parents=True, exist_ok=True)

        data = {}
        for key, value in config.__dict__.items():
            # Convert Path objects to strings for JSON serialization
            if isinstance(value, Path):
                data[key] = str(value)
            else:
                data[key] = value

        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return True

    except OSError as e:
        print(f"Warning: Could not save config ({e}).")
        return False


def update_config(updates: dict) -> AppConfig:
    """
    Load config, apply updates, save, and return the updated config.
    """
    config = load_config()
    for key, value in updates.items():
        if hasattr(config, key):
            setattr(config, key, value)
    save_config(config)
    return config


def reset_config() -> AppConfig:
    """Reset configuration to defaults."""
    config = AppConfig()
    save_config(config)
    return config
