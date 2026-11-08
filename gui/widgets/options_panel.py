from PySide6.QtWidgets import (
    QWidget, QGroupBox, QVBoxLayout, QCheckBox, QHBoxLayout, 
    QLabel, QSpinBox, QDoubleSpinBox, QLineEdit, QComboBox, QPushButton, QMessageBox,
    QScrollArea
)
from PySide6.QtCore import Qt

from core.languages import name_of
from gui.theme import Colors
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

# (label shown in the UI, value stored in ProcessingOptions.subtitle_charset)
CHARSET_CHOICES = [
    ("Auto-detect (recommended)", "auto"),
    ("UTF-8", "utf-8"),
    ("Windows-1256 (Arabic)", "cp1256"),
]

try:
    from core.models import ProcessingOptions
    from core.constants import DEFAULT_PARALLEL_WORKERS, MAX_PARALLEL_WORKERS, MIN_PARALLEL_WORKERS
    from core.config import load_config, save_config
except ImportError:
    ProcessingOptions = None
    DEFAULT_PARALLEL_WORKERS = 4
    MAX_PARALLEL_WORKERS = 8
    MIN_PARALLEL_WORKERS = 1
    load_config = None
    save_config = None


class OptionsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("optionsPanelContainer")
        self.config = load_config() if load_config else None

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
        scroll_layout.setContentsMargins(0, 0, 8, 0)
        scroll_layout.setSpacing(4)

        
        # --- Presets Group ---
        preset_group = QGroupBox("PRESET")
        preset_layout = QHBoxLayout(preset_group)
        
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Default")
        if self.config and self.config.presets:
            for name in self.config.presets:
                self.preset_combo.addItem(name)
        
        self.preset_combo.currentTextChanged.connect(self._load_preset)
        
        save_preset_btn = QPushButton("SAVE")
        save_preset_btn.clicked.connect(self._save_preset)
        
        del_preset_btn = QPushButton("DEL")
        del_preset_btn.clicked.connect(self._delete_preset)
        
        preset_layout.addWidget(self.preset_combo, 1)
        preset_layout.addWidget(save_preset_btn)
        preset_layout.addWidget(del_preset_btn)
        
        # --- Filters Group ---
        filter_group = QGroupBox("TRACK FILTERS")
        filter_layout = QVBoxLayout(filter_group)
        
        self.audio_input = MultiLanguageCombo("All audio tracks (nothing ticked)")
        self.audio_input.set_values(["jpn"])
        self.sub_input = MultiLanguageCombo("None — remove all original subtitles")
        filter_layout.addWidget(self._field("KEEP AUDIO", self.audio_input))
        filter_layout.addWidget(self._field("KEEP ORIGINAL SUBS", self.sub_input))

        # --- New Subtitle Group (timing + encoding) ---
        subtitle_group = QGroupBox("NEW SUBTITLE")
        subtitle_layout = QVBoxLayout(subtitle_group)

        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setRange(-600.0, 600.0)
        self.offset_spin.setDecimals(3)
        self.offset_spin.setSingleStep(0.1)
        self.offset_spin.setSuffix(" s")
        self.offset_spin.setValue(0.0)
        self.offset_spin.setToolTip("Positive = subtitle shows later (delay). Negative = shows earlier.")

        self.charset_combo = QComboBox()
        for label, value in CHARSET_CHOICES:
            self.charset_combo.addItem(label, value)
        self.charset_combo.setToolTip("Fixes Arabic text that shows up as garbage symbols.")

        # Language + track name of the subtitle being added (defaults come from Settings)
        default_lang = (self.config.subtitle_language if self.config else "") or "ara"
        default_name = (self.config.subtitle_name if self.config else "") or name_of(default_lang)
        self.sub_lang_combo = LanguageCombo()
        self.sub_lang_combo.set_value(default_lang)
        self.sub_name_edit = QLineEdit(default_name)
        self.sub_name_edit.setPlaceholderText("Name shown in the player")
        _follow_language(self.sub_lang_combo, self.sub_name_edit)

        subtitle_layout.addWidget(self._field("LANGUAGE", self.sub_lang_combo))
        subtitle_layout.addWidget(self._field("TRACK NAME", self.sub_name_edit))
        subtitle_layout.addWidget(self._field("SHIFT TIMING   ( + LATER / − EARLIER )", self.offset_spin))
        subtitle_layout.addWidget(self._field("ENCODING", self.charset_combo))

        # --- Track Metadata Editor Group ---
        editor_group = QGroupBox("FIX EXISTING TRACK")
        editor_layout = QVBoxLayout(editor_group)

        self.edit_target = LanguageCombo(empty_label="Off — don't change any track",
                                         include_undetermined=True)
        self.edit_new_lang = LanguageCombo()
        self.edit_new_lang.set_value("ara")
        self.edit_new_name = QLineEdit("Arabic")
        _follow_language(self.edit_new_lang, self.edit_new_name)
        editor_layout.addWidget(self._field("TRACK LANGUAGE TO FIX", self.edit_target))
        editor_layout.addWidget(self._field("CHANGE IT TO", self.edit_new_lang))
        editor_layout.addWidget(self._field("NEW TRACK NAME", self.edit_new_name))

        self.isolate_track_cb = QCheckBox("Remove all other original subtitles")
        self.isolate_track_cb.setChecked(False)
        editor_layout.addWidget(self.isolate_track_cb)

        # --- General Group ---
        general_group = QGroupBox("OUTPUT")
        general_layout = QVBoxLayout(general_group)

        self.subfolder_cb = QCheckBox("Save into a PROCESSED/ subfolder")
        self.subfolder_cb.setChecked(True)

        self.dry_run_cb = QCheckBox("Dry run (simulate, write nothing)")

        self.worker_spin = QSpinBox()
        self.worker_spin.setRange(MIN_PARALLEL_WORKERS, MAX_PARALLEL_WORKERS)
        self.worker_spin.setValue(DEFAULT_PARALLEL_WORKERS)

        general_layout.addWidget(self.subfolder_cb)
        general_layout.addWidget(self.dry_run_cb)
        general_layout.addWidget(self._field("EPISODES AT ONCE", self.worker_spin))

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
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(4)
        cap = QLabel(label)
        cap.setProperty("role", "fieldLabel")
        cap.setStyleSheet(f"color: {Colors.text_muted}; font-size: 10px;")
        lay.addWidget(cap)
        lay.addWidget(widget)
        return box

    def _load_preset(self, name: str):
        if not self.config or name == "Default":
            self.audio_input.set_values(["jpn"])
            self.sub_input.set_values([])
            self.edit_target.set_value("")
            self.edit_new_lang.set_value("ara")
            self.edit_new_name.setText("Arabic")
            lang = (self.config.subtitle_language if self.config else "") or "ara"
            self.sub_lang_combo.set_value(lang)
            self.sub_name_edit.setText((self.config.subtitle_name if self.config else "") or name_of(lang))
            self.isolate_track_cb.setChecked(False)
            self.subfolder_cb.setChecked(True)
            self.dry_run_cb.setChecked(False)
            self.worker_spin.setValue(DEFAULT_PARALLEL_WORKERS)
            self.offset_spin.setValue(0.0)
            self._set_charset("auto")
            return
            
        preset = self.config.presets.get(name)
        if preset:
            self.audio_input.set_values(preset.get("keep_audio_langs", ["jpn"]))
            self.sub_input.set_values(preset.get("keep_sub_langs", []))
            self.edit_target.set_value(preset.get("edit_target_lang", ""))
            self.edit_new_lang.set_value(preset.get("edit_new_lang", "ara"))
            self.edit_new_name.setText(preset.get("edit_new_name", "Arabic"))
            self.sub_lang_combo.set_value(preset.get("subtitle_language", "ara"))
            self.sub_name_edit.setText(preset.get("subtitle_name", name_of(self.sub_lang_combo.value())))
            self.isolate_track_cb.setChecked(preset.get("isolate_edited_track", False))
            self.subfolder_cb.setChecked(preset.get("create_output_folder", True))
            self.dry_run_cb.setChecked(preset.get("dry_run", False))
            self.worker_spin.setValue(preset.get("workers", DEFAULT_PARALLEL_WORKERS))
            self.offset_spin.setValue(preset.get("subtitle_offset_ms", 0) / 1000.0)
            self._set_charset(preset.get("subtitle_charset", "auto"))

    def _set_charset(self, value: str):
        idx = self.charset_combo.findData(value)
        self.charset_combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _save_preset(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Save Preset", "Enter preset name:")
        if ok and name and self.config and save_config:
            opts = self.get_options()
            preset_dict = {
                "keep_audio_langs": opts.keep_audio_langs,
                "keep_sub_langs": opts.keep_sub_langs,
                "edit_target_lang": opts.edit_target_lang,
                "edit_new_lang": opts.edit_new_lang,
                "edit_new_name": opts.edit_new_name,
                "isolate_edited_track": opts.isolate_edited_track,
                "create_output_folder": opts.create_output_folder,
                "backup_originals": opts.backup_originals,
                "dry_run": opts.dry_run,
                "workers": opts.workers,
                "subtitle_offset_ms": opts.subtitle_offset_ms,
                "subtitle_charset": opts.subtitle_charset,
                "subtitle_language": opts.subtitle_language,
                "subtitle_name": opts.subtitle_name
            }
            if not self.config.presets:
                self.config.presets = {}
            self.config.presets[name] = preset_dict
            save_config(self.config)
            
            # Update UI
            if self.preset_combo.findText(name) == -1:
                self.preset_combo.addItem(name)
            self.preset_combo.setCurrentText(name)
            
    def _delete_preset(self):
        name = self.preset_combo.currentText()
        if name == "Default" or not self.config or not self.config.presets:
            return
            
        if name in self.config.presets:
            del self.config.presets[name]
            if save_config:
                save_config(self.config)
            idx = self.preset_combo.findText(name)
            self.preset_combo.removeItem(idx)

    def get_options(self):
        """Return a ProcessingOptions with the current UI values."""
        if ProcessingOptions:
            audio_langs = self.audio_input.values()
            sub_langs = self.sub_input.values()
            sub_lang = self.sub_lang_combo.value() or "ara"

            return ProcessingOptions(
                subtitle_language=sub_lang,
                subtitle_name=self.sub_name_edit.text().strip() or name_of(sub_lang),
                create_output_folder=self.subfolder_cb.isChecked(),
                dry_run=self.dry_run_cb.isChecked(),
                parallel_workers=self.worker_spin.value(),
                workers=self.worker_spin.value(),
                keep_audio_langs=audio_langs,
                keep_sub_langs=sub_langs,
                edit_target_lang=self.edit_target.value(),
                edit_new_lang=self.edit_new_lang.value() or "ara",
                edit_new_name=self.edit_new_name.text().strip(),
                isolate_edited_track=self.isolate_track_cb.isChecked(),
                subtitle_offset_ms=round(self.offset_spin.value() * 1000),
                subtitle_charset=self.charset_combo.currentData() or "auto"
            )
        return None
