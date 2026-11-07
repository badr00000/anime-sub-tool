from PySide6.QtWidgets import (
    QWidget, QGroupBox, QVBoxLayout, QCheckBox, QHBoxLayout, 
    QLabel, QSpinBox, QLineEdit, QComboBox, QPushButton, QMessageBox,
    QScrollArea
)
from PySide6.QtCore import Qt

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
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        
        content_widget = QWidget()
        content_widget.setStyleSheet("QWidget { background: transparent; }")
        
        scroll_layout = QVBoxLayout(content_widget)
        scroll_layout.setContentsMargins(0, 0, 10, 0)

        
        # --- Presets Group ---
        preset_group = QGroupBox("Configuration Presets")
        preset_layout = QHBoxLayout(preset_group)
        
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Default")
        if self.config and self.config.presets:
            for name in self.config.presets:
                self.preset_combo.addItem(name)
        
        self.preset_combo.currentTextChanged.connect(self._load_preset)
        
        save_preset_btn = QPushButton("Save As")
        save_preset_btn.clicked.connect(self._save_preset)
        
        del_preset_btn = QPushButton("Delete")
        del_preset_btn.clicked.connect(self._delete_preset)
        
        preset_layout.addWidget(self.preset_combo, 1)
        preset_layout.addWidget(save_preset_btn)
        preset_layout.addWidget(del_preset_btn)
        
        # --- Filters Group ---
        filter_group = QGroupBox("Advanced Filters")
        filter_layout = QVBoxLayout(filter_group)
        
        audio_layout = QHBoxLayout()
        audio_layout.addWidget(QLabel("Keep Audio Langs:"))
        self.audio_input = QLineEdit("jpn")
        self.audio_input.setPlaceholderText("e.g. jpn, eng (empty to strip all)")
        audio_layout.addWidget(self.audio_input, 1)
        
        sub_layout = QHBoxLayout()
        sub_layout.addWidget(QLabel("Keep Subtitle Langs:"))
        self.sub_input = QLineEdit("")
        self.sub_input.setPlaceholderText("e.g. ara, eng (empty to strip all original)")
        sub_layout.addWidget(self.sub_input, 1)
        
        filter_layout.addLayout(audio_layout)
        filter_layout.addLayout(sub_layout)

        # --- Track Metadata Editor Group ---
        editor_group = QGroupBox("🔧 Modify Existing Tracks")
        editor_layout = QVBoxLayout(editor_group)
        
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Target Track Lang:"))
        self.edit_target = QLineEdit("")
        self.edit_target.setPlaceholderText("e.g. und (empty to disable)")
        row1.addWidget(self.edit_target)
        
        row1.addWidget(QLabel("Convert To:"))
        self.edit_new_lang = QLineEdit("ara")
        row1.addWidget(self.edit_new_lang)
        
        row1.addWidget(QLabel("New Name:"))
        self.edit_new_name = QLineEdit("Arabic")
        row1.addWidget(self.edit_new_name)
        
        editor_layout.addLayout(row1)
        
        self.isolate_track_cb = QCheckBox("🗑️ Delete all other original subtitles except this one")
        self.isolate_track_cb.setChecked(False)
        editor_layout.addWidget(self.isolate_track_cb)

        # --- General Group ---
        general_group = QGroupBox("General Options")
        general_layout = QVBoxLayout(general_group)

        self.subfolder_cb = QCheckBox("Create output subfolder (PROCESSED/)")
        self.subfolder_cb.setChecked(True)

        self.backup_cb = QCheckBox("Keep original files (backup)")
        self.backup_cb.setChecked(False)

        self.dry_run_cb = QCheckBox("Dry run (simulate only)")

        worker_layout = QHBoxLayout()
        worker_label = QLabel("Worker threads:")
        self.worker_spin = QSpinBox()
        self.worker_spin.setRange(MIN_PARALLEL_WORKERS, MAX_PARALLEL_WORKERS)
        self.worker_spin.setValue(DEFAULT_PARALLEL_WORKERS)
        self.worker_spin.setFixedWidth(60)
        worker_layout.addWidget(worker_label)
        worker_layout.addWidget(self.worker_spin)
        worker_layout.addStretch()

        general_layout.addWidget(self.subfolder_cb)
        general_layout.addWidget(self.backup_cb)
        general_layout.addWidget(self.dry_run_cb)
        general_layout.addLayout(worker_layout)

        scroll_layout.addWidget(preset_group)
        scroll_layout.addWidget(filter_group)
        scroll_layout.addWidget(editor_group)
        scroll_layout.addWidget(general_group)
        scroll_layout.addStretch()
        
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)
        
    def _load_preset(self, name: str):
        if not self.config or name == "Default":
            self.audio_input.setText("jpn")
            self.sub_input.setText("")
            self.edit_target.setText("")
            self.edit_new_lang.setText("ara")
            self.edit_new_name.setText("Arabic")
            self.isolate_track_cb.setChecked(False)
            self.subfolder_cb.setChecked(True)
            self.backup_cb.setChecked(False)
            self.dry_run_cb.setChecked(False)
            self.worker_spin.setValue(DEFAULT_PARALLEL_WORKERS)
            return
            
        preset = self.config.presets.get(name)
        if preset:
            self.audio_input.setText(",".join(preset.get("keep_audio_langs", ["jpn"])))
            self.sub_input.setText(",".join(preset.get("keep_sub_langs", [])))
            self.edit_target.setText(preset.get("edit_target_lang", ""))
            self.edit_new_lang.setText(preset.get("edit_new_lang", "ara"))
            self.edit_new_name.setText(preset.get("edit_new_name", "Arabic"))
            self.isolate_track_cb.setChecked(preset.get("isolate_edited_track", False))
            self.subfolder_cb.setChecked(preset.get("create_output_folder", True))
            self.backup_cb.setChecked(preset.get("backup_originals", False))
            self.dry_run_cb.setChecked(preset.get("dry_run", False))
            self.worker_spin.setValue(preset.get("workers", DEFAULT_PARALLEL_WORKERS))

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
                "workers": opts.workers
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
            audio_langs = [x.strip() for x in self.audio_input.text().split(",") if x.strip()]
            sub_langs = [x.strip() for x in self.sub_input.text().split(",") if x.strip()]
            
            return ProcessingOptions(
                create_output_folder=self.subfolder_cb.isChecked(),
                create_backup=self.backup_cb.isChecked(),
                backup_originals=self.backup_cb.isChecked(),
                keep_original=self.backup_cb.isChecked(),
                dry_run=self.dry_run_cb.isChecked(),
                parallel_workers=self.worker_spin.value(),
                workers=self.worker_spin.value(),
                keep_audio_langs=audio_langs,
                keep_sub_langs=sub_langs,
                edit_target_lang=self.edit_target.text().strip(),
                edit_new_lang=self.edit_new_lang.text().strip(),
                edit_new_name=self.edit_new_name.text().strip(),
                isolate_edited_track=self.isolate_track_cb.isChecked()
            )
        return None
