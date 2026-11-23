from PySide6.QtWidgets import (
    QWidget, QGroupBox, QVBoxLayout, QCheckBox, QHBoxLayout,
    QLabel, QSpinBox, QDoubleSpinBox, QLineEdit, QComboBox, QPushButton,
    QScrollArea
)
from PySide6.QtCore import Qt

from core.config import DEFAULT_PRESET_NAME, clean_preset, is_reserved_preset_name, save_config
from core.constants import MAX_OFFSET_MS, MAX_PARALLEL_WORKERS, MIN_PARALLEL_WORKERS
from core.languages import name_of
from core.models import AppConfig, ProcessingOptions
from core.subtitles import CHARSET_CHOICES
from gui.widgets.language_picker import LanguageCombo, MultiLanguageCombo


def _follow_language(combo: "LanguageCombo", name_edit: QLineEdit) -> None:
    """Keep the track name in step with the language ('Arabic' -> 'English'),
    unless the user typed a custom name."""
    state = {"last": combo.value()}

    def on_change(_):
        new = combo.value()
        current = name_edit.text().strip()
        if not current or current == name_of(state["last"]):
            name_edit.setText(name_of(new))
        state["last"] = new

    combo.currentIndexChanged.connect(on_change)


class OptionsPanel(QWidget):
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.setObjectName("optionsPanelContainer")
        # The window's own AppConfig, not a second copy: two copies saved from two
        # places would overwrite each other's changes on disk.
        self.config = config

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        content_widget = QWidget()
        # Only this container is transparent: a plain "QWidget {...}" rule here would also
        # cascade into every dropdown popup and make their lists see-through.
        content_widget.setObjectName("optionsContent")
        content_widget.setStyleSheet("#optionsContent { background: transparent; }")

        scroll_layout = QVBoxLayout(content_widget)
        scroll_layout.setContentsMargins(0, 0, 16, 0)
        scroll_layout.setSpacing(0)


        # --- Presets Group ---
        preset_group = QGroupBox("Preset")
        preset_layout = QHBoxLayout(preset_group)

        self.preset_combo = QComboBox()
        self.preset_combo.addItem(DEFAULT_PRESET_NAME)
        for name in self.config.presets:
            if not is_reserved_preset_name(name):     # load_config() renames those
                self.preset_combo.addItem(name)

        self.preset_combo.currentTextChanged.connect(self._load_preset)

        save_preset_btn = QPushButton("Save")
        save_preset_btn.clicked.connect(self._save_preset)

        del_preset_btn = QPushButton("Delete")
        del_preset_btn.clicked.connect(self._delete_preset)

        preset_layout.addWidget(self.preset_combo, 1)
        preset_layout.addWidget(save_preset_btn)
        preset_layout.addWidget(del_preset_btn)

        # --- Filters Group ---
        filter_group = QGroupBox("Tracks to keep")
        filter_layout = QVBoxLayout(filter_group)

        self.audio_input = MultiLanguageCombo("All audio tracks (nothing ticked)")
        self.audio_input.set_values(["jpn"])
        filter_layout.addWidget(self._field("Audio languages", self.audio_input))

        # Original subtitles inside the episode: remove them (default) or keep them all
        self.remove_subs_cb = QCheckBox("Remove the subtitles already inside")
        self.remove_subs_cb.setChecked(True)
        self.remove_subs_cb.setToolTip("Unticked: every subtitle already in the episode is kept,\n"
                                       "and the new subtitle is added next to them.")
        self.sub_input = MultiLanguageCombo("None, remove them all")
        self._sub_except_field = self._field("Except these languages", self.sub_input)
        self.remove_subs_cb.toggled.connect(self._sub_except_field.setEnabled)
        filter_layout.addSpacing(4)
        filter_layout.addWidget(self.remove_subs_cb)
        filter_layout.addWidget(self._sub_except_field)

        # --- New Subtitle Group (timing + encoding) ---
        subtitle_group = QGroupBox("New subtitle")
        subtitle_layout = QVBoxLayout(subtitle_group)

        self.offset_spin = QDoubleSpinBox()
        # Same limit as the CLI and saved presets, so no preset is clamped silently
        self.offset_spin.setRange(-MAX_OFFSET_MS / 1000, MAX_OFFSET_MS / 1000)
        self.offset_spin.setDecimals(3)
        self.offset_spin.setSingleStep(0.1)
        self.offset_spin.setSuffix(" s")
        self.offset_spin.setValue(0.0)
        self.offset_spin.setToolTip("Positive = subtitle shows later (delay). Negative = shows earlier.")

        self.charset_combo = QComboBox()
        for label, value in CHARSET_CHOICES:
            self.charset_combo.addItem(label, value)
        self.charset_combo.setToolTip("Fixes subtitle text that shows up as garbage symbols.\n"
                                      "Pick it by hand when the preview marks the encoding uncertain.")

        # Language + track name of the subtitle being added (defaults come from Settings)
        default_lang = self.config.subtitle_language or "ara"
        default_name = self.config.subtitle_name or name_of(default_lang)
        self.sub_lang_combo = LanguageCombo()
        self.sub_lang_combo.set_value(default_lang)
        self.sub_name_edit = QLineEdit(default_name)
        self.sub_name_edit.setPlaceholderText("Name shown in the player")
        _follow_language(self.sub_lang_combo, self.sub_name_edit)

        subtitle_layout.addWidget(self._field("Language", self.sub_lang_combo))
        subtitle_layout.addWidget(self._field("Track name", self.sub_name_edit))
        subtitle_layout.addWidget(self._field("Timing shift (positive shows later)", self.offset_spin))
        subtitle_layout.addWidget(self._field("Encoding", self.charset_combo))

        # --- Track Metadata Editor Group ---
        editor_group = QGroupBox("Fix an existing track")
        editor_layout = QVBoxLayout(editor_group)

        self.edit_target = LanguageCombo(empty_label="Off",
                                         include_undetermined=True)
        self.edit_new_lang = LanguageCombo()
        self.edit_new_lang.set_value("ara")
        self.edit_new_name = QLineEdit("Arabic")
        _follow_language(self.edit_new_lang, self.edit_new_name)
        editor_layout.addWidget(self._field("Track language to fix", self.edit_target))
        editor_layout.addWidget(self._field("Change it to", self.edit_new_lang))
        editor_layout.addWidget(self._field("New track name", self.edit_new_name))

        self.isolate_track_cb = QCheckBox("Remove all other original subtitles")
        self.isolate_track_cb.setChecked(False)
        editor_layout.addWidget(self.isolate_track_cb)

        # --- General Group ---
        general_group = QGroupBox("Output")
        general_layout = QVBoxLayout(general_group)

        self.subfolder_cb = QCheckBox()
        self.subfolder_cb.setChecked(True)
        self.subfolder_cb.setToolTip("Unticked: the new files are saved next to the episodes,\n"
                                     "with [AnimeSubTool] added to their names.")

        self.overwrite_cb = QCheckBox("Overwrite existing output files")
        self.overwrite_cb.setToolTip("Unticked: an episode whose output file already exists is skipped.")

        self.unmatched_cb = QCheckBox("Also process episodes that have no subtitle")
        self.unmatched_cb.setToolTip("Unticked: episodes without a matching subtitle are skipped.\n"
                                     "Ticked: they are still cleaned (audio / subtitle filters), "
                                     "with no subtitle added.")

        self.dry_run_cb = QCheckBox("Dry run, write nothing")

        self.worker_spin = QSpinBox()
        self.worker_spin.setRange(MIN_PARALLEL_WORKERS, MAX_PARALLEL_WORKERS)
        self.worker_spin.setValue(self.config.default_workers)
        self._update_subfolder_label()

        general_layout.addWidget(self.subfolder_cb)
        general_layout.addWidget(self.overwrite_cb)
        general_layout.addWidget(self.unmatched_cb)
        general_layout.addWidget(self.dry_run_cb)
        general_layout.addWidget(self._field("Episodes at once", self.worker_spin))

        scroll_layout.addWidget(preset_group)
        scroll_layout.addWidget(filter_group)
        scroll_layout.addWidget(subtitle_group)
        scroll_layout.addWidget(editor_group)
        scroll_layout.addWidget(general_group)
        scroll_layout.addStretch()

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

    @staticmethod
    def _field(label: str, widget: QWidget) -> QWidget:
        """A small caption above an input, so fields fit a narrow column."""
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(4)
        cap = QLabel(label)
        cap.setProperty("role", "fieldLabel")
        lay.addWidget(cap)
        lay.addWidget(widget)
        return box

    def _update_subfolder_label(self):
        self.subfolder_cb.setText(f"Save into a {self.config.output_subfolder}/ subfolder")

    def apply_config_defaults(self):
        """Settings were saved: show the new defaults."""
        self._update_subfolder_label()
        self.sub_lang_combo.set_value(self.config.subtitle_language)
        self.sub_name_edit.setText(self.config.subtitle_name or name_of(self.config.subtitle_language))
        self.worker_spin.setValue(self.config.default_workers)

    def _load_preset(self, name: str):
        """Fill the form from a preset. 'Default' (or an unknown name) gives the defaults.

        Preset values come from a hand-editable file: each one is type-checked and a
        bad or missing value simply leaves the default in place.
        """
        preset = {} if name == DEFAULT_PRESET_NAME else clean_preset(self.config.presets.get(name))
        lang = preset.get("subtitle_language") or self.config.subtitle_language or "ara"
        if name == DEFAULT_PRESET_NAME:
            sub_name = self.config.subtitle_name or name_of(lang)
        else:
            sub_name = preset.get("subtitle_name") or name_of(lang)

        self.audio_input.set_values(preset.get("keep_audio_langs", ["jpn"]))
        self.remove_subs_cb.setChecked(preset.get("remove_existing_subs", True))
        self.sub_input.set_values(preset.get("keep_sub_langs", []))
        self.edit_target.set_value(preset.get("edit_target_lang", ""))
        self.edit_new_lang.set_value(preset.get("edit_new_lang") or "ara")
        self.edit_new_name.setText(preset.get("edit_new_name", "Arabic"))
        self.sub_lang_combo.set_value(lang)
        self.sub_name_edit.setText(sub_name)
        self.isolate_track_cb.setChecked(preset.get("isolate_edited_track", False))
        self.subfolder_cb.setChecked(preset.get("create_output_folder", True))
        self.overwrite_cb.setChecked(preset.get("overwrite_existing", False))
        self.unmatched_cb.setChecked(preset.get("process_unmatched", False))
        self.dry_run_cb.setChecked(preset.get("dry_run", False))
        self.worker_spin.setValue(preset.get("workers", self.config.default_workers))
        self.offset_spin.setValue(preset.get("subtitle_offset_ms", 0) / 1000.0)
        self._set_charset(preset.get("subtitle_charset", "auto"))

    def _set_charset(self, value: str):
        idx = self.charset_combo.findData(value)
        self.charset_combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _save_preset(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Save Preset", "Enter preset name:")
        if ok and name.strip() and not self.save_preset(name.strip()):
            from gui.dialogs import messages
            messages.warn(self, "Save Preset",
                          f"'{DEFAULT_PRESET_NAME}' is the built-in preset and cannot be "
                          "replaced. Pick another name.")

    def save_preset(self, name: str) -> bool:
        """Store the current form as a preset and write the shared config to disk.
        False (nothing saved) for the reserved name 'Default'."""
        name = name.strip()
        if not name or is_reserved_preset_name(name):
            return False
        opts = self.get_options()
        self.config.presets[name] = {
            "keep_audio_langs": opts.keep_audio_langs,
            "keep_sub_langs": opts.keep_sub_langs,
            "remove_existing_subs": opts.remove_existing_subs,
            "edit_target_lang": opts.edit_target_lang,
            "edit_new_lang": opts.edit_new_lang,
            "edit_new_name": opts.edit_new_name,
            "isolate_edited_track": opts.isolate_edited_track,
            "create_output_folder": opts.create_output_folder,
            "overwrite_existing": opts.overwrite_existing,
            "process_unmatched": opts.process_unmatched,
            "dry_run": opts.dry_run,
            "workers": opts.parallel_workers,
            "subtitle_offset_ms": opts.subtitle_offset_ms,
            "subtitle_charset": opts.subtitle_charset,
            "subtitle_language": opts.subtitle_language,
            "subtitle_name": opts.subtitle_name,
        }
        save_config(self.config)

        if self.preset_combo.findText(name) == -1:
            self.preset_combo.addItem(name)
        self.preset_combo.setCurrentText(name)
        return True

    def _delete_preset(self):
        name = self.preset_combo.currentText()
        if name == DEFAULT_PRESET_NAME:
            return
        if name in self.config.presets:
            del self.config.presets[name]
            save_config(self.config)
        self.preset_combo.removeItem(self.preset_combo.findText(name))

    def get_options(self) -> ProcessingOptions:
        """Return a ProcessingOptions with the current UI values."""
        sub_lang = self.sub_lang_combo.value() or "ara"

        options = ProcessingOptions.from_config(self.config)
        options.subtitle_language = sub_lang
        options.subtitle_name = self.sub_name_edit.text().strip() or name_of(sub_lang)
        options.create_output_folder = self.subfolder_cb.isChecked()
        options.overwrite_existing = self.overwrite_cb.isChecked()
        options.process_unmatched = self.unmatched_cb.isChecked()
        options.dry_run = self.dry_run_cb.isChecked()
        options.parallel_workers = self.worker_spin.value()
        options.keep_audio_langs = self.audio_input.values()
        options.keep_sub_langs = self.sub_input.values()
        options.remove_existing_subs = self.remove_subs_cb.isChecked()
        options.edit_target_lang = self.edit_target.value()
        options.edit_new_lang = self.edit_new_lang.value() or "ara"
        options.edit_new_name = self.edit_new_name.text().strip()
        options.isolate_edited_track = self.isolate_track_cb.isChecked()
        options.subtitle_offset_ms = round(self.offset_spin.value() * 1000)
        options.subtitle_charset = self.charset_combo.currentData() or "auto"
        return options
