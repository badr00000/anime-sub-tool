import json
import logging

import pytest

from core import config as cfg
from core.config import clean_preset, load_config, save_config
from core.constants import LOG_FILE_NAME
from core.models import AppConfig, ProcessingOptions
from utils.logger import get_logger, setup_logging
from utils.paths import get_app_data_dir


def write_raw(data: bytes):
    path = cfg._get_config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_config_lives_in_the_redirected_home(isolated_home):
    assert cfg._get_config_file().parent.parent == isolated_home


def test_missing_file_gives_defaults():
    assert load_config() == AppConfig()
    assert AppConfig().mkvtoolnix_path == ""        # empty = bundled mkvmerge


@pytest.mark.parametrize("raw", [
    b"[]", b"null", b'"x"', b"5", b"true", b"", b"{", b"\xff\xfe\x00garbage", b"\x80\x81\x82",
    b'{"subtitle_language": 5}', b'{"subtitle_name": 5}', b'{"presets": "abc"}',
    b'{"presets": ["a"]}', b'{"presets": {"p": "abc"}}', b'{"default_workers": "4"}',
    b'{"default_workers": true}', b'{"mkvtoolnix_path": null}', b'{"output_subfolder": 7}',
    b'{"output_subfolder": "..\\\\..\\\\x"}', b'{"output_subfolder": "C:/x"}',
])
def test_corrupt_or_wrong_typed_config_falls_back_to_defaults(raw):
    write_raw(raw)
    assert load_config() == AppConfig()


def test_bad_keys_fall_back_individually():
    write_raw(json.dumps({
        "subtitle_language": 5,                 # bad -> default
        "subtitle_name": "English subs",        # good
        "default_workers": 99,                  # clamped
        "output_subfolder": "DONE",
        "mkvtoolnix_path": "D:/tools",
        "presets": {"ok": {"workers": 2}, "bad": "abc", "": {"workers": 1}},
        # keys of older versions must load without error
        "last_folder": "C:/x", "theme": "dark", "window_width": 1, "create_backup": True,
        "watch_folder_enabled": True, "show_preview": False,
    }).encode())
    config = load_config()
    assert config.subtitle_language == "ara"
    assert config.subtitle_name == "English subs"
    assert config.default_workers == 8
    assert config.output_subfolder == "DONE"
    assert config.mkvtoolnix_path == "D:/tools"
    assert config.presets == {"ok": {"workers": 2}}
    assert not hasattr(config, "last_folder")


def test_clean_preset_type_checks_every_value():
    assert clean_preset("abc") == {}
    assert clean_preset(None) == {}
    cleaned = clean_preset({
        "workers": "x", "keep_audio_langs": "jpn", "keep_sub_langs": ["eng", 5],
        "remove_existing_subs": "yes", "dry_run": 1, "subtitle_offset_ms": "100",
        "subtitle_charset": 5, "subtitle_language": None, "backup_originals": True,
        "edit_new_name": ["x"], "create_output_folder": None,
    })
    assert cleaned == {}
    good = {
        "workers": 3, "keep_audio_langs": ["jpn", "eng"], "keep_sub_langs": [],
        "remove_existing_subs": False, "dry_run": True, "subtitle_offset_ms": 1500,
        "subtitle_charset": "cp1256", "subtitle_language": "eng", "subtitle_name": "English",
        "overwrite_existing": True, "process_unmatched": True, "create_output_folder": False,
        "isolate_edited_track": True, "edit_target_lang": "und", "edit_new_lang": "ara",
        "edit_new_name": "Arabic",
    }
    assert clean_preset(good) == good
    assert clean_preset({"workers": 500})["workers"] == 8
    assert clean_preset({"subtitle_offset_ms": 1500.4})["subtitle_offset_ms"] == 1500


def test_save_round_trip():
    config = AppConfig(mkvtoolnix_path="", default_workers=2, output_subfolder="OUT",
                       subtitle_language="eng", subtitle_name="English",
                       presets={"mine": {"workers": 3, "keep_audio_langs": ["jpn"]}})
    assert save_config(config)
    assert load_config() == config
    assert not list(cfg._get_config_dir().glob("*.tmp"))


def test_one_shared_instance_keeps_settings_and_presets():
    """Settings and presets are saved from the same AppConfig, so neither wipes the other."""
    config = load_config()
    config.presets["p1"] = {"workers": 2}
    save_config(config)                     # what saving a preset does
    config.subtitle_language = "eng"
    config.default_workers = 6
    save_config(config)                     # what saving Settings does
    on_disk = load_config()
    assert on_disk.presets == {"p1": {"workers": 2}}
    assert on_disk.subtitle_language == "eng" and on_disk.default_workers == 6
    config.presets["p2"] = {"dry_run": True}
    save_config(config)
    on_disk = load_config()
    assert set(on_disk.presets) == {"p1", "p2"} and on_disk.subtitle_language == "eng"


def test_options_take_defaults_from_config():
    config = AppConfig(default_workers=7, output_subfolder="OUT", subtitle_language="eng",
                       subtitle_name="English")
    options = ProcessingOptions.from_config(config)
    assert (options.parallel_workers, options.output_folder) == (7, "OUT")
    assert (options.subtitle_language, options.subtitle_name) == ("eng", "English")
    assert options.overwrite_existing is False and options.process_unmatched is False


def test_dead_fields_are_gone():
    for name in ("series_name", "create_backup", "backup_originals", "keep_original", "workers",
                 "output_suffix"):
        assert not hasattr(ProcessingOptions(), name)
    for name in ("last_folder", "theme", "window_width", "watch_folder_enabled", "show_preview",
                 "remember_settings", "create_backup", "last_series_name"):
        assert not hasattr(AppConfig(), name)


def test_logging_goes_to_one_rotating_file():
    log_dir = get_app_data_dir() / "logs"
    root = setup_logging()
    try:
        assert not log_dir.exists() or not list(log_dir.iterdir())   # nothing logged, no empty file
        get_logger("core.batch").warning("hello from a module")
        for handler in root.handlers:
            handler.flush()
        files = list(log_dir.iterdir())
        assert [f.name for f in files] == [LOG_FILE_NAME]
        assert "hello from a module" in files[0].read_text(encoding="utf-8")
        setup_logging()                                             # again: no duplicate handlers
        assert len([h for h in root.handlers if isinstance(h, logging.FileHandler)]) == 1
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
            handler.close()
        root.propagate = True
