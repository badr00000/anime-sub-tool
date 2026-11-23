"""
Sync Subtitle page — a standalone tool, separate from season merging.

Play an episode with a subtitle drawn on top, shift the subtitle earlier/later
while watching (G / H like VLC), then save a shifted copy of the subtitle file.
The video and the original subtitle are never modified.
"""

from bisect import bisect_right
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, QSizeF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QPen, QShortcut, QTextOption
from PySide6.QtMultimedia import QAudioOutput, QMediaMetaData, QMediaPlayer
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFileDialog, QFrame, QGraphicsRectItem, QGraphicsScene,
    QGraphicsTextItem, QGraphicsView, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSlider, QVBoxLayout, QWidget,
)

from core import subtitle_file as sf
from core.constants import MAX_OFFSET_MS, VIDEO_EXTENSIONS
from core.subtitles import (
    CHARSET_AUTO, CHARSET_CHOICES, ENCODING_UNCERTAIN, UNCERTAIN_HINT, describe_encoding,
)
from gui.dialogs import messages
from gui.icons import icon
from gui.theme import Colors, page_header, plain_tooltip

VIDEO_EXTS = VIDEO_EXTENSIONS
SUB_EXTS = sf.SUPPORTED_EXTENSIONS
STEP_SMALL = 50       # G / H, same as VLC
SEEK_STEP = 5000      # ← / →


def _keys_text() -> str:
    """Keyboard shortcuts as small keycaps."""
    cap = (f"<span style='font-family: Consolas; color: {Colors.text_secondary};"
           f" background: {Colors.raised};'>&nbsp;{{}}&nbsp;</span>")
    return (f"{cap.format('G')} earlier &nbsp; {cap.format('H')} later<br>"
            f"{cap.format('Space')} play &nbsp; {cap.format('←')} {cap.format('→')} 5 s")


def _clock(ms: int) -> str:
    s = max(0, int(ms)) // 1000
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class CueTimeline(QWidget):
    """A window of the episode around the playhead: where each subtitle line sits.

    Faint outlines are the lines at their original time, filled blocks are where
    they land with the current offset, so the shift is visible as it happens.
    """

    WINDOW_MS = 12_000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)
        self._cues: list = []
        self._offset = 0
        self._pos = 0

    def set_state(self, cues, offset_ms: int, position_ms: int):
        if (cues is self._cues and offset_ms == self._offset and position_ms == self._pos):
            return
        self._cues, self._offset, self._pos = cues, offset_ms, position_ms
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(QPen(QColor(Colors.hairline), 1))
        p.setBrush(QColor(Colors.surface))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 10, 10)

        start = self._pos - self.WINDOW_MS // 2
        scale = w / self.WINDOW_MS
        x_of = lambda ms: (ms - start) * scale

        # One tick per second, a time label every two seconds
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPixelSize(10)
        p.setFont(font)
        first = (start // 1000 + 1) * 1000
        for ms in range(first, start + self.WINDOW_MS, 1000):
            if ms < 0:
                continue
            x = x_of(ms)
            p.setPen(QPen(QColor(Colors.hairline_strong), 1))
            p.drawLine(QPointF(x, h - 14), QPointF(x, h - 10))
            if (ms // 1000) % 2 == 0:
                p.setPen(QColor(Colors.text_muted))
                p.drawText(QRectF(x - 30, h - 12, 60, 12), Qt.AlignmentFlag.AlignCenter, _clock(ms))

        lane = QRectF(0, 12, w, 22)
        for cue in self._cues:
            if cue.end_ms + abs(self._offset) < start or cue.start_ms - abs(self._offset) > start + self.WINDOW_MS:
                continue
            original = QRectF(x_of(cue.start_ms), lane.y(), max(2.0, (cue.end_ms - cue.start_ms) * scale),
                              lane.height())
            shifted = original.translated(self._offset * scale, 0)
            if self._offset:
                pen = QPen(QColor(Colors.hairline_strong), 1)
                pen.setDashPattern([3, 3])
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(original, 5, 5)
            p.setPen(QPen(QColor(Colors.accent), 1))
            p.setBrush(QColor(Colors.accent_soft))
            p.drawRoundedRect(shifted, 5, 5)

        # Playhead
        x = x_of(self._pos)
        p.setPen(QPen(QColor(Colors.text), 1.5))
        p.drawLine(QPointF(x, 6), QPointF(x, h - 16))
        p.end()


class VideoView(QGraphicsView):
    """Video with a subtitle box drawn on top (a plain QVideoWidget cannot be overlaid)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMinimumSize(420, 240)

        self.video_item = QGraphicsVideoItem()
        self.scene().addItem(self.video_item)

        self._sub_bg = QGraphicsRectItem()
        self._sub_bg.setBrush(QColor(0, 0, 0, 165))
        self._sub_bg.setPen(Qt.PenStyle.NoPen)
        self._sub_bg.setZValue(1)
        self.scene().addItem(self._sub_bg)

        self._sub = QGraphicsTextItem()
        self._sub.setDefaultTextColor(QColor("#ffffff"))
        self._sub.setZValue(2)
        opt = QTextOption(Qt.AlignmentFlag.AlignHCenter)
        opt.setWrapMode(QTextOption.WrapMode.WordWrap)
        self._sub.document().setDefaultTextOption(opt)
        self.scene().addItem(self._sub)

        self._message = QGraphicsTextItem()
        self._message.setDefaultTextColor(QColor(Colors.text_muted))
        self._message.setZValue(3)
        self.scene().addItem(self._message)

        self._text = ""
        self.set_message("Drop an episode and its subtitle here")

    def set_message(self, text: str):
        self._message.setPlainText(text)
        self._message.setVisible(bool(text))
        self._layout()

    def set_subtitle(self, text: str):
        if text == self._text:
            return
        self._text = text
        self._sub.setPlainText(text)
        self._layout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout()

    def _layout(self):
        w, h = self.viewport().width(), self.viewport().height()
        self.scene().setSceneRect(0, 0, w, h)
        self.video_item.setSize(QSizeF(w, h))
        self.video_item.setPos(0, 0)

        mf = QFont("Segoe UI")
        mf.setPixelSize(14)
        self._message.setFont(mf)
        br = self._message.boundingRect()
        self._message.setPos((w - br.width()) / 2, (h - br.height()) / 2)

        visible = bool(self._text)
        self._sub.setVisible(visible)
        self._sub_bg.setVisible(visible)
        if not visible:
            return
        f = QFont("Segoe UI", 10)
        f.setPixelSize(max(14, int(h * 0.05)))
        f.setWeight(QFont.Weight.DemiBold)
        self._sub.setFont(f)
        self._sub.setTextWidth(w * 0.86)
        br = self._sub.boundingRect()
        x = (w - br.width()) / 2
        y = h - br.height() - h * 0.06
        self._sub.setPos(x, y)
        self._sub_bg.setRect(QRectF(x - 8, y + 2, br.width() + 16, br.height() - 4))


class FileField(QWidget):
    """Caption + read-only path + Browse."""

    browse_clicked = Signal()

    def __init__(self, caption: str, placeholder: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        cap = QLabel(caption)
        cap.setProperty("role", "fieldLabel")
        row = QHBoxLayout()
        row.setSpacing(6)
        self.edit = QLineEdit()
        self.edit.setReadOnly(True)
        self.edit.setPlaceholderText(placeholder)
        btn = QPushButton("Browse")
        btn.setFixedHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self.browse_clicked.emit)
        row.addWidget(self.edit, 1)
        row.addWidget(btn)
        lay.addWidget(cap)
        lay.addLayout(row)


class SyncPage(QWidget):
    status_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._sub: sf.SubtitleFile | None = None
        self._starts: list[int] = []
        self._cues: list[sf.Cue] = []
        self._offset = 0
        self._saved_offset = 0
        self._seeking = False

        # ── player ──
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.8)
        self.player.setAudioOutput(self.audio)
        self.view = VideoView()
        self.player.setVideoOutput(self.view.video_item)
        self.player.durationChanged.connect(self._on_duration)
        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.errorOccurred.connect(self._on_error)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.tracksChanged.connect(self._fill_audio_tracks)

        self._tick = QTimer(self)
        self._tick.setInterval(40)
        self._tick.timeout.connect(self._refresh)
        self._tick.start()

        # ── layout ──
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(20)
        root.addWidget(page_header(
            "Sync a subtitle",
            "Play the episode, move the subtitle until it matches the voice, then save a synced copy."))

        files = QHBoxLayout()
        files.setSpacing(16)
        self.video_field = FileField("Episode", "Pick or drop a video file")
        self.video_field.browse_clicked.connect(self._browse_video)
        self.sub_field = FileField("Subtitle", "Pick or drop a .srt or .ass file")
        self.sub_field.browse_clicked.connect(self._browse_subtitle)
        files.addWidget(self.video_field, 1)
        files.addWidget(self.sub_field, 1)
        root.addLayout(files)

        body = QHBoxLayout()
        body.setSpacing(20)
        root.addLayout(body, 1)

        # Left: video + transport
        left = QVBoxLayout()
        left.setSpacing(12)
        left.addWidget(self.view, 1)
        self.timeline = CueTimeline()
        left.addWidget(self.timeline)

        transport = QHBoxLayout()
        transport.setSpacing(12)
        self.play_btn = QPushButton()
        self.play_btn.setIcon(icon("play", Colors.text))
        self.play_btn.setIconSize(QSize(16, 16))
        self.play_btn.setToolTip("Play / pause (Space)")
        self.play_btn.setFixedSize(36, 36)
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.clicked.connect(self.toggle_play)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self.seek.sliderReleased.connect(self._seek_released)
        self.time_lbl = QLabel("00:00 / 00:00")
        self.time_lbl.setProperty("role", "mono")
        self.audio_combo = QComboBox()
        self.audio_combo.setMinimumWidth(150)
        self.audio_combo.setToolTip("Audio track")
        self.audio_combo.currentIndexChanged.connect(self._on_audio_track)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(80)
        self.volume.setFixedWidth(80)
        self.volume.setToolTip("Volume")
        self.volume.valueChanged.connect(lambda v: self.audio.setVolume(v / 100))
        transport.addWidget(self.play_btn)
        transport.addWidget(self.seek, 1)
        transport.addWidget(self.time_lbl)
        transport.addWidget(self.audio_combo)
        transport.addWidget(self.volume)
        left.addLayout(transport)
        body.addLayout(left, 1)

        # Right: sync controls
        panel = QFrame()
        panel.setObjectName("card")
        panel.setFixedWidth(300)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(20, 20, 20, 20)
        pl.setSpacing(8)

        enc_cap = QLabel("Subtitle encoding")
        enc_cap.setProperty("role", "fieldLabel")
        self.encoding_combo = QComboBox()
        for label, value in CHARSET_CHOICES:
            self.encoding_combo.addItem(label, value)
        self.encoding_combo.setToolTip("Reload the subtitle with another encoding when its "
                                       "text shows up as garbage.")
        self.encoding_combo.currentIndexChanged.connect(self._on_encoding_chosen)
        # Shown when auto-detect could not tell the encoding of the loaded file
        self.encoding_warn = QLabel(f"Subtitle {UNCERTAIN_HINT} above. The text may look "
                                    "garbled, and it cannot be saved until you do.")
        self.encoding_warn.setTextFormat(Qt.TextFormat.PlainText)
        self.encoding_warn.setProperty("role", "warn")
        self.encoding_warn.setWordWrap(True)
        self.encoding_warn.hide()

        cap = QLabel("Offset")
        cap.setProperty("role", "fieldLabel")
        self.offset_lbl = QLabel()
        self.offset_lbl.setStyleSheet(f"font-family: {Colors.font_mono}; font-size: 28px; font-weight: 500;"
                                      f" color: {Colors.text}; background: transparent;")
        self.offset_hint = QLabel()
        self.offset_hint.setProperty("role", "hint")
        # Shown when the offset pushes lines before 0:00 (they cannot be saved as they are)
        self.clamp_lbl = QLabel("")
        self.clamp_lbl.setTextFormat(Qt.TextFormat.PlainText)
        self.clamp_lbl.setProperty("role", "warn")
        self.clamp_lbl.setWordWrap(True)
        self.clamp_lbl.hide()

        grid = QGridLayout()
        grid.setSpacing(8)
        for col, (label, ms, tip) in enumerate([("−1s", -1000, "1 second earlier"),
                                                ("−100", -100, "100 ms earlier"),
                                                ("−50", -STEP_SMALL, "50 ms earlier  (G)")]):
            grid.addWidget(self._nudge(label, ms, tip), 0, col)
        for col, (label, ms, tip) in enumerate([("+50", STEP_SMALL, "50 ms later  (H)"),
                                                ("+100", 100, "100 ms later"),
                                                ("+1s", 1000, "1 second later")]):
            grid.addWidget(self._nudge(label, ms, tip), 1, col)

        exact_cap = QLabel("Exact value")
        exact_cap.setProperty("role", "fieldLabel")
        exact_row = QHBoxLayout()
        self.exact = QDoubleSpinBox()
        self.exact.setRange(-MAX_OFFSET_MS / 1000, MAX_OFFSET_MS / 1000)
        self.exact.setDecimals(3)
        self.exact.setSingleStep(0.05)
        self.exact.setSuffix(" s")
        self.exact.valueChanged.connect(lambda v: self.set_offset(round(v * 1000), from_spin=True))
        reset = QPushButton("Reset")
        reset.setObjectName("ghostButton")
        reset.clicked.connect(lambda: self.set_offset(0))
        exact_row.addWidget(self.exact, 1)
        exact_row.addWidget(reset)

        line_cap = QLabel("On screen now")
        line_cap.setProperty("role", "fieldLabel")
        # Subtitle text comes straight from a file: plain text only, or markup in a
        # subtitle (e.g. an <img> pointing at a local file) would be rendered.
        self.line_lbl = QLabel("—")
        self.line_lbl.setTextFormat(Qt.TextFormat.PlainText)
        self.line_lbl.setWordWrap(True)
        self.line_lbl.setMinimumHeight(44)
        self.line_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.line_lbl.setStyleSheet(f"color: {Colors.text}; background: {Colors.input};"
                                    f" border: 1px solid {Colors.hairline}; border-radius: 8px; padding: 8px;")

        keys = QLabel(_keys_text())
        keys.setTextFormat(Qt.TextFormat.RichText)
        keys.setProperty("role", "hint")

        self.save_btn = QPushButton("Save synced copy")
        self.save_btn.setObjectName("primaryButton")
        self.save_btn.setFixedHeight(40)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.clicked.connect(self.save)
        self.save_as_btn = QPushButton("Save as…")
        self.save_as_btn.setFixedHeight(36)
        self.save_as_btn.clicked.connect(self.save_as)
        self.saved_lbl = QLabel("")
        self.saved_lbl.setTextFormat(Qt.TextFormat.PlainText)
        self.saved_lbl.setWordWrap(True)
        self.saved_lbl.setProperty("role", "ok")

        pl.addWidget(enc_cap)
        pl.addWidget(self.encoding_combo)
        pl.addWidget(self.encoding_warn)
        pl.addSpacing(12)
        pl.addWidget(cap)
        pl.addWidget(self.offset_lbl)
        pl.addWidget(self.offset_hint)
        pl.addWidget(self.clamp_lbl)
        pl.addSpacing(4)
        pl.addLayout(grid)
        pl.addSpacing(8)
        pl.addWidget(exact_cap)
        pl.addLayout(exact_row)
        pl.addSpacing(8)
        pl.addWidget(line_cap)
        pl.addWidget(self.line_lbl)
        pl.addStretch(1)
        pl.addWidget(keys)
        pl.addSpacing(8)
        pl.addWidget(self.save_btn)
        pl.addWidget(self.save_as_btn)
        pl.addWidget(self.saved_lbl)
        body.addWidget(panel)

        # ── keyboard (only while this page is shown) ──
        for key, slot in ((Qt.Key.Key_G, lambda: self.nudge(-STEP_SMALL)),
                          (Qt.Key.Key_H, lambda: self.nudge(STEP_SMALL)),
                          (Qt.Key.Key_Space, self.toggle_play),
                          (Qt.Key.Key_Left, lambda: self.seek_by(-SEEK_STEP)),
                          (Qt.Key.Key_Right, lambda: self.seek_by(SEEK_STEP))):
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)

        self.set_offset(0)
        self._update_buttons()

    # ── helpers ──
    def _nudge(self, label: str, ms: int, tip: str) -> QPushButton:
        b = QPushButton(label)
        b.setObjectName("nudgeButton")
        b.setToolTip(tip)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # keep Space for play/pause
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda: self.nudge(ms))
        return b

    def _update_buttons(self):
        has_sub = self._sub is not None
        self.save_btn.setEnabled(has_sub)
        self.save_as_btn.setEnabled(has_sub)
        self.play_btn.setEnabled(bool(self.player.source().toString()))

    # ── offset ──
    def nudge(self, ms: int):
        self.set_offset(self._offset + ms)

    def set_offset(self, ms: int, from_spin: bool = False):
        self._offset = int(ms)
        self.offset_lbl.setText(sf.format_offset(self._offset))
        self.offset_hint.setText("The subtitle shows later" if ms > 0 else
                                 "The subtitle shows earlier" if ms < 0 else "Original timing")
        if not from_spin:
            self.exact.blockSignals(True)
            self.exact.setValue(self._offset / 1000)
            self.exact.blockSignals(False)
        if self._offset != self._saved_offset:
            self.saved_lbl.setText("")
        self._update_clamp_warning()
        self._refresh()

    def clamped_lines(self) -> int:
        return sf.count_clamped(self._sub, self._offset) if self._sub else 0

    def _update_clamp_warning(self):
        clamped = self.clamped_lines()
        if clamped:
            self.clamp_lbl.setText(f"{clamped} line(s) would start before 0:00 and "
                                   "will be squeezed to 0:00 in the saved file")
        self.clamp_lbl.setVisible(bool(clamped))

    # ── loading ──
    def load_video(self, path: str):
        p = Path(path)
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(str(p)))
        self.video_field.edit.setText(str(p))
        self.video_field.edit.setToolTip(plain_tooltip(str(p)))
        self.view.set_message("Loading…")
        if self._sub is None:
            self._auto_pick_subtitle(p)
        self._update_buttons()

    def _auto_pick_subtitle(self, video: Path):
        """Same folder: a subtitle with the same name, else the only one with the same episode number."""
        same = [video.with_suffix(ext) for ext in (".srt", ".ass", ".ssa")]
        for cand in same:
            if cand.exists():
                self.load_subtitle(str(cand))
                return
        try:
            from core.matcher import extract_episode_info
            ep = extract_episode_info(video).episode_num
            if not ep:
                return
            hits = [f for f in video.parent.iterdir()
                    if f.suffix.lower() in SUB_EXTS and extract_episode_info(f).episode_num == ep]
            if len(hits) == 1:
                self.load_subtitle(str(hits[0]))
        except OSError:
            pass

    def _on_encoding_chosen(self, index: int):
        """Reload the current subtitle with the encoding picked in the list."""
        if self._sub is None or index < 0:
            return
        value = self.encoding_combo.itemData(index)
        self.load_subtitle(str(self._sub.path), None if value == CHARSET_AUTO else value)

    def _show_encoding(self, chosen: str | None):
        """Select `chosen` (None = Auto) in the list without reloading, and show the
        warning while the encoding of the loaded file is uncertain."""
        self.encoding_combo.blockSignals(True)
        self.encoding_combo.setCurrentIndex(max(0, self.encoding_combo.findData(chosen or CHARSET_AUTO)))
        self.encoding_combo.blockSignals(False)
        self.encoding_warn.setVisible(self._sub is not None
                                      and self._sub.encoding == ENCODING_UNCERTAIN)

    def load_subtitle(self, path: str, encoding: str | None = None):
        """Load a subtitle; `encoding` (an id from the Encoding list) skips detection."""
        try:
            sub = sf.load(path, encoding)
        except (OSError, ValueError) as e:
            messages.warn(self, "Subtitle", f"Could not read this subtitle:\n\n{e}")
            return
        if not sub.cues:
            messages.warn(self, "Subtitle",
                          f"No subtitle lines were found in:\n\n{Path(path).name}\n\n"
                          "The file is empty or damaged.")
            return
        # Re-reading the same file in another encoding keeps the offset found so far
        same_file = self._sub is not None and sf.is_same_file(self._sub.path, path)
        self._sub = sub
        self._cues = sorted(sub.cues, key=lambda c: c.start_ms)
        self._starts = [c.start_ms for c in self._cues]
        if not same_file:
            self._saved_offset = 0
        self.sub_field.edit.setText(path)
        described = describe_encoding(sub.encoding)
        self.sub_field.edit.setToolTip(plain_tooltip(
            f"{path}\n{len(self._cues)} lines · encoding {described}"))
        self.saved_lbl.setText("")
        self._show_encoding(encoding)
        self.set_offset(self._offset if same_file else 0)
        status = f"Loaded {len(self._cues)} subtitle lines ({described})"
        if sub.encoding == ENCODING_UNCERTAIN:
            status += f" — {UNCERTAIN_HINT}"
        self.status_message.emit(status)
        self._update_buttons()

    def _browse_video(self):
        exts = " ".join(f"*{e}" for e in sorted(VIDEO_EXTS))
        path, _ = QFileDialog.getOpenFileName(self, "Choose episode", self._start_dir(),
                                              f"Video ({exts})")
        if path:
            self.load_video(path)

    def _browse_subtitle(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose subtitle", self._start_dir(),
                                              "Subtitles (*.srt *.ass *.ssa)")
        if path:
            self.load_subtitle(path)

    def _start_dir(self) -> str:
        for text in (self.video_field.edit.text(), self.sub_field.edit.text()):
            if text:
                return str(Path(text).parent)
        return ""

    # ── drag & drop ──
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.suffix.lower() in SUB_EXTS:
                self.load_subtitle(str(p))
            elif p.suffix.lower() in VIDEO_EXTS:
                self.load_video(str(p))

    # ── playback ──
    def toggle_play(self):
        if not self.player.source().toString():
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def seek_by(self, ms: int):
        self.player.setPosition(max(0, self.player.position() + ms))

    def _seek_released(self):
        self._seeking = False
        self.player.setPosition(self.seek.value())

    def _on_duration(self, ms: int):
        self.seek.setRange(0, ms)

    def _on_state(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_btn.setIcon(icon("pause" if playing else "play", Colors.text))

    def _on_media_status(self, status):
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            self.view.set_message("")
            # Hide subtitles embedded in the video so only the one being synced is shown
            self.player.setActiveSubtitleTrack(-1)
            if status == QMediaPlayer.MediaStatus.LoadedMedia and \
                    self.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState:
                self.player.play()
                self.player.pause()  # show the first frame
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self.view.set_message("This video can't be played here")

    def _on_error(self, error, message: str):
        if error != QMediaPlayer.Error.NoError:
            self.view.set_message("This video can't be played here. Its codec may not be supported")
            self.status_message.emit(f"Video error: {message}")

    def _fill_audio_tracks(self):
        tracks = self.player.audioTracks()
        self.audio_combo.blockSignals(True)
        self.audio_combo.clear()
        preferred = 0
        for i, meta in enumerate(tracks):
            lang = meta.value(QMediaMetaData.Key.Language)
            lang_name = lang.name if hasattr(lang, "name") else str(lang or "")
            title = meta.stringValue(QMediaMetaData.Key.Title)
            label = " · ".join(x for x in (lang_name.replace("AnyLanguage", ""), title) if x) or f"Track {i + 1}"
            self.audio_combo.addItem(label, i)
            if "Japanese" in lang_name and preferred == 0:
                preferred = i
        self.audio_combo.setCurrentIndex(preferred if tracks else -1)
        self.audio_combo.blockSignals(False)
        self.audio_combo.setVisible(len(tracks) > 1)
        if tracks:
            self.player.setActiveAudioTrack(preferred)
        self.player.setActiveSubtitleTrack(-1)

    def _on_audio_track(self, idx: int):
        if idx >= 0:
            self.player.setActiveAudioTrack(self.audio_combo.itemData(idx))

    def _refresh(self):
        pos = self.player.position()
        if not self._seeking:
            self.seek.blockSignals(True)
            self.seek.setValue(pos)
            self.seek.blockSignals(False)
        self.time_lbl.setText(f"{_clock(pos)} / {_clock(self.player.duration())}")

        text = ""
        if self._cues:
            t = pos - self._offset            # time on the subtitle's own clock
            i = bisect_right(self._starts, t)
            active = [c.text for c in self._cues[max(0, i - 30):i] if c.end_ms > t]
            text = "\n".join(active)
        self.view.set_subtitle(text)
        self.line_lbl.setText(text or "—")
        self.timeline.set_state(self._cues, self._offset, pos)

    # ── saving ──
    def save(self):
        if not self._sub:
            return
        target = sf.default_output_path(self._sub.path)
        self._write(target)

    def save_as(self):
        if not self._sub:
            return
        default = str(sf.default_output_path(self._sub.path))
        path, _ = QFileDialog.getSaveFileName(self, "Save synced subtitle", default,
                                              f"Subtitle (*{self._sub.path.suffix})")
        if path:
            self._write(path)

    def _confirm_overwrite_source(self, target: Path) -> bool:
        return messages.confirm(
            self, "Overwrite the loaded subtitle?",
            f"{target.name}\n\nis the subtitle file that is loaded right now. Saving here "
            "replaces it with the shifted version and the current timing is lost.\n\n"
            "Overwrite it?")

    def _write(self, target):
        if not self._sub:
            return
        target = Path(target)
        if self._sub.encoding == ENCODING_UNCERTAIN:
            # Saving would write the unreadable characters into the copy for good
            messages.warn(self, "Choose the encoding first",
                          f"The subtitle {UNCERTAIN_HINT} (SUBTITLE ENCODING, on the right). "
                          "Pick the one that makes the text readable, then save.")
            return
        if sf.all_cues_gone(self._sub, self._offset):
            messages.warn(self, "Offset too large",
                          f"A {sf.format_offset(self._offset)} shift moves every line to or before "
                          "0:00, so the saved subtitle would show nothing. Use a smaller offset.")
            return
        # Saving onto the loaded file (Save As onto it, or Save for a file that is
        # already a '.synced' copy) destroys the source: only after an explicit yes.
        force = False
        if sf.is_same_file(target, self._sub.path):
            if not self._confirm_overwrite_source(target):
                return
            force = True
        try:
            out = sf.save_shifted(self._sub, self._offset, target, force=force)
        except (OSError, ValueError) as e:
            messages.error(self, "Save failed", f"Could not save the subtitle:\n\n{e}")
            return
        self._saved_offset = self._offset
        self.saved_lbl.setText(f"Saved {out.name} ({sf.format_offset(self._offset)})")
        self.status_message.emit(f"Saved synced subtitle: {out}")

    def pause(self):
        """Called when the user leaves this page."""
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()

    def shutdown(self):
        self._tick.stop()
        self.player.stop()
