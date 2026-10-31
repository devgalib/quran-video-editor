"""Main window: settings on the left, live preview and render controls on the right.

The widgets are the source of truth. collect() turns them into a job dict (the same format
as a project file) and apply() does the reverse, so Open/Save/Render all share one path.
"""

import copy
import json
import os
import random

from PySide6.QtCore import QSettings, Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..cards import TEMPLATES
from ..config import DEFAULTS, deep_merge, prepare_job
from .surahs import SURAHS
from .workers import RenderThread, Task, hw_encoders, make_preview, probe_video, scan_folder

GOLD = "#E3B85C"
TRANSITIONS = ["fade", "dissolve", "fadeblack", "fadewhite", "smoothleft", "smoothright",
               "smoothup", "smoothdown", "circleopen", "circleclose", "wipeleft", "wiperight",
               "slideleft", "slideright", "radial", "hblur"]
TEMPLATE_NAMES = {
    "royal": "Royal (centred, gold)", "minimal": "Minimal (modern)", "frame": "Frame (gold panel)",
    "corner": "Corner tag", "bismillah": "Bismillah (glow)", "bismillah_frame": "Bismillah (panel)",
}
NEW_CARD = {"template": "royal", "start": 0, "duration": 6.5, "fade": 0.8, "animation": "rise"}
PREVIEW_SIZE = (960, 540)
VIDEO_FILTER = "Videos (*.mp4 *.mov *.mkv *.webm *.avi *.m4v);;All files (*)"


def dspin(lo, hi, step=0.5, decimals=1, suffix=" s"):
    w = QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setSingleStep(step)
    w.setDecimals(decimals)
    w.setSuffix(suffix)
    return w


def ispin(lo, hi, suffix=""):
    w = QSpinBox()
    w.setRange(lo, hi)
    w.setSuffix(suffix)
    return w


def hslider(lo, hi):
    w = QSlider(Qt.Orientation.Horizontal)
    w.setRange(lo, hi)
    return w


def path_row(edit, on_browse):
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    btn = QPushButton("Browse…")
    btn.clicked.connect(on_browse)
    lay.addWidget(edit, 1)
    lay.addWidget(btn)
    return row


def fmt_time(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


class PreviewLabel(QLabel):
    """Shows the preview image scaled to fit, keeping 16:9."""

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(480, 270)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background:#07090c; border-radius:8px; color:#6b7380;")
        self._pix = None

    def set_image(self, qimage):
        self._pix = QPixmap.fromImage(qimage)
        self._rescale()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self):
        if self._pix:
            self.setPixmap(self._pix.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Quran Video Editor")
        self.settings = QSettings("QuranVideoEditor", "qve")
        self.pool = QThreadPool.globalInstance()
        self.project_path = None
        self.cards = []
        self.quran_info = None
        self.clips = []
        self.bg_clip = None
        self.render_thread = None
        self._threads = set()  # finished threads are kept until Qt reports them stopped
        self._loading = False
        self._preview_gen = 0
        self._want_time = None  # preview time to show once the video length is known
        self._loaded_paths = {}  # what on_quran_changed / on_bg_changed last loaded

        self.preview_timer = QTimer(self, singleShot=True, interval=180)
        self.preview_timer.timeout.connect(self.refresh_preview)

        self._build_menu()
        splitter = QSplitter()
        splitter.addWidget(self._build_settings())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([470, 900])
        self.setCentralWidget(splitter)
        self.resize(1400, 860)
        if self.settings.value("geometry"):
            self.restoreGeometry(self.settings.value("geometry"))

        last = self.settings.value("last_job")
        self.apply(deep_merge(DEFAULTS, json.loads(last)) if last else copy.deepcopy(DEFAULTS))
        self._start(Task("encoders", hw_encoders))

    # ---- layout ---------------------------------------------------------------------------

    def _build_menu(self):
        menu = self.menuBar().addMenu("&File")
        for text, key, slot in (("&New project", QKeySequence.StandardKey.New, self.new_project),
                                ("&Open project…", QKeySequence.StandardKey.Open, self.open_project),
                                ("&Save project", QKeySequence.StandardKey.Save, self.save_project),
                                ("Save project &as…", QKeySequence.StandardKey.SaveAs,
                                 lambda: self.save_project(ask=True))):
            act = QAction(text, self)
            act.setShortcut(key)
            act.triggered.connect(slot)
            menu.addAction(act)
        menu.addSeparator()
        quit_act = QAction("&Quit", self)
        quit_act.setShortcut(QKeySequence.StandardKey.Quit)
        quit_act.triggered.connect(self.close)
        menu.addAction(quit_act)

    def _group(self, title, layout):
        box = QGroupBox(title)
        box.setLayout(layout)
        return box

    def _build_settings(self):
        col = QVBoxLayout()
        col.setSpacing(10)

        # Recitation
        f = QFormLayout()
        self.quran_edit = QLineEdit(placeholderText="Recitation video with black or green background")
        self.quran_edit.editingFinished.connect(self.on_quran_changed)
        f.addRow("Video", path_row(self.quran_edit, self.browse_quran))
        self.quran_info_label = QLabel("")
        self.quran_info_label.setStyleSheet("color:#8a93a0;")
        f.addRow("", self.quran_info_label)
        self.key_combo = QComboBox()
        self.key_combo.addItem("Black background (screen blend)", "screen")
        self.key_combo.addItem("Green screen (chroma key)", "chromakey")
        f.addRow("Remove", self.key_combo)
        self.key_color_btn = QPushButton()
        self.key_color_btn.clicked.connect(self.pick_key_color)
        self.similarity = dspin(0.01, 0.5, 0.01, 2, "")
        key_row = QWidget()
        kl = QHBoxLayout(key_row)
        kl.setContentsMargins(0, 0, 0, 0)
        kl.addWidget(self.key_color_btn)
        kl.addWidget(QLabel("Similarity"))
        kl.addWidget(self.similarity)
        self.key_row_label = QLabel("Key colour")
        f.addRow(self.key_row_label, key_row)
        self.intro = dspin(0, 60)
        self.outro = dspin(0, 60)
        f.addRow("Intro before recitation", self.intro)
        f.addRow("Outro after recitation", self.outro)
        col.addWidget(self._group("Recitation", f))

        # Titles
        f = QFormLayout()
        self.surah_combo = QComboBox()
        self.surah_combo.addItem("Choose surah…", None)
        for n, en, ar, meaning in SURAHS:
            self.surah_combo.addItem(f"{n}. {en}  —  {ar}", (n, en, ar, meaning))
        self.surah_combo.activated.connect(self.on_surah_picked)
        f.addRow("Surah", self.surah_combo)
        self.meta_edits = {}
        for key, label in (("surah_ar", "Arabic name"), ("surah_en", "English name"),
                           ("surah_meaning", "Meaning"), ("surah_number", "Number"),
                           ("reciter", "Reciter"), ("channel", "Channel")):
            edit = QLineEdit()
            if key == "surah_ar":
                edit.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self.meta_edits[key] = edit
            f.addRow(label, edit)
        col.addWidget(self._group("Titles", f))

        # Backgrounds
        f = QFormLayout()
        self.bg_edit = QLineEdit(placeholderText="Folder with your background clips")
        self.bg_edit.editingFinished.connect(self.on_bg_changed)
        f.addRow("Clip folder", path_row(self.bg_edit, self.browse_bg))
        self.bg_info = QLabel("")
        self.bg_info.setStyleSheet("color:#8a93a0;")
        f.addRow("", self.bg_info)
        self.max_clip = dspin(4, 120, 1, 0)
        f.addRow("Max time per clip", self.max_clip)
        self.dim = hslider(0, 90)
        self.dim_label = QLabel()
        self.dim.valueChanged.connect(lambda v: self.dim_label.setText(f"{v}%"))
        dim_row = QWidget()
        dl = QHBoxLayout(dim_row)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.addWidget(self.dim, 1)
        dl.addWidget(self.dim_label)
        f.addRow("Darken", dim_row)
        self.blur = dspin(0, 30, 1, 0, "")
        f.addRow("Blur", self.blur)
        self.random_start = QCheckBox("Start long clips at a random point")
        f.addRow("", self.random_start)
        col.addWidget(self._group("Background clips", f))

        # Transitions
        f = QFormLayout()
        self.trans_dur = dspin(0.2, 3, 0.1, 1)
        f.addRow("Duration", self.trans_dur)
        self.trans_order = QComboBox()
        self.trans_order.addItem("Random", "random")
        self.trans_order.addItem("In turn", "cycle")
        f.addRow("Order", self.trans_order)
        self.trans_list = QListWidget()
        self.trans_list.setFixedHeight(130)
        for name in TRANSITIONS:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.trans_list.addItem(item)
        f.addRow("Types", self.trans_list)
        col.addWidget(self._group("Transitions", f))

        # Cards
        v = QVBoxLayout()
        self.card_list = QListWidget()
        self.card_list.setFixedHeight(96)
        self.card_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.card_list.currentRowChanged.connect(self.on_card_selected)
        v.addWidget(self.card_list)
        btns = QHBoxLayout()
        for text, slot in (("Add", self.add_card), ("Remove", self.remove_card)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            btns.addWidget(b)
        btns.addStretch(1)
        v.addLayout(btns)
        self.card_form = QWidget()
        cf = QFormLayout(self.card_form)
        cf.setContentsMargins(0, 4, 0, 0)
        self.c_template = QComboBox()
        for key in TEMPLATES:
            self.c_template.addItem(TEMPLATE_NAMES.get(key, key), key)
        cf.addRow("Template", self.c_template)
        self.c_start = dspin(-600, 7200)
        self.c_start.setToolTip("Seconds from the start. Negative = seconds before the end.")
        self.c_duration = dspin(1, 600)
        self.c_fade = dspin(0, 3, 0.1, 1)
        cf.addRow("Starts at", self.c_start)
        cf.addRow("Shown for", self.c_duration)
        cf.addRow("Fade", self.c_fade)
        self.c_anim = QComboBox()
        self.c_anim.addItem("Fade and rise", "rise")
        self.c_anim.addItem("Fade only", "fade")
        cf.addRow("Animation", self.c_anim)
        self.c_accent = QPushButton()
        self.c_accent.clicked.connect(self.pick_accent)
        cf.addRow("Accent colour", self.c_accent)
        self.c_backdrop = hslider(0, 100)
        cf.addRow("Shade behind text", self.c_backdrop)
        self.c_position = QComboBox()
        self.c_position.addItem("Top left", "top")
        self.c_position.addItem("Bottom left", "bottom")
        self.c_position_label = QLabel("Position")
        cf.addRow(self.c_position_label, self.c_position)
        self.c_translation = QCheckBox("Show English meaning")
        cf.addRow("", self.c_translation)
        v.addWidget(self.card_form)
        col.addWidget(self._group("Text cards", v))

        # Output
        f = QFormLayout()
        self.out_dir = QLineEdit()
        f.addRow("Folder", path_row(self.out_dir, self.browse_out))
        self.out_name = QLineEdit()
        self.out_name.setToolTip("{surah_en}, {surah_ar}, {surah_number}, {reciter}, {channel}")
        f.addRow("File name", self.out_name)
        self.resolution = QComboBox()
        for label, wh in (("1080p (1920×1080)", (1920, 1080)), ("720p (1280×720)", (1280, 720)),
                          ("1440p (2560×1440)", (2560, 1440))):
            self.resolution.addItem(label, wh)
        f.addRow("Size", self.resolution)
        self.fps = QComboBox()
        for n in (30, 25, 24, 60):
            self.fps.addItem(f"{n} fps", n)
        f.addRow("Frame rate", self.fps)
        self.encoder = QComboBox()
        self.encoder.addItem("CPU (x264)", "libx264")
        f.addRow("Encoder", self.encoder)
        self.quality = ispin(14, 32)
        self.quality.setToolTip("Lower = better quality and bigger file. 18–22 is good for YouTube.")
        f.addRow("Quality (lower = better)", self.quality)
        self.preset = QComboBox()
        for p in ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium"):
            self.preset.addItem(p, p)
        f.addRow("Speed preset", self.preset)
        self.threads = ispin(1, os.cpu_count() or 4)
        self.threads.setToolTip("Fewer threads = cooler laptop, slower render")
        f.addRow("CPU threads", self.threads)
        col.addWidget(self._group("Output", f))
        col.addStretch(1)

        inner = QWidget()
        inner.setLayout(col)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        scroll.setMinimumWidth(440)

        # every edit refreshes the preview
        for w in (self.similarity, self.intro, self.outro, self.max_clip, self.blur, self.trans_dur,
                  self.c_start, self.c_duration, self.c_fade):
            w.valueChanged.connect(self.changed)
        for w in (self.dim, self.c_backdrop):
            w.valueChanged.connect(self.changed)
        for w in (self.key_combo, self.c_template, self.c_anim, self.c_position):
            w.currentIndexChanged.connect(self.changed)
        for w in list(self.meta_edits.values()):
            w.textChanged.connect(self.changed)
        self.c_translation.toggled.connect(self.changed)
        self.trans_list.itemChanged.connect(self.changed)
        for w in (self.c_template, self.c_start, self.c_duration, self.c_fade, self.c_anim,
                  self.c_backdrop, self.c_position, self.c_translation):
            sig = getattr(w, "currentIndexChanged", None) or getattr(w, "valueChanged", None) \
                or w.toggled
            sig.connect(self.store_card)
        self.key_combo.currentIndexChanged.connect(self._update_visibility)
        self.c_template.currentIndexChanged.connect(self._update_visibility)
        return scroll

    def _build_right(self):
        right = QWidget()
        v = QVBoxLayout(right)
        tabs = QTabWidget()

        pv = QWidget()
        pl = QVBoxLayout(pv)
        self.preview = PreviewLabel()
        self.preview.setText("Choose a recitation video and a clip folder")
        pl.addWidget(self.preview, 1)
        row = QHBoxLayout()
        self.time_slider = hslider(0, 0)
        self.time_slider.valueChanged.connect(self.on_time_changed)
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setMinimumWidth(90)
        shuffle = QPushButton("Another clip")
        shuffle.setToolTip("Show a different background clip in the preview")
        shuffle.clicked.connect(self.shuffle_clip)
        row.addWidget(self.time_slider, 1)
        row.addWidget(self.time_label)
        row.addWidget(shuffle)
        pl.addLayout(row)
        tabs.addTab(pv, "Preview")

        self.log = QPlainTextEdit(readOnly=True)
        self.log.setStyleSheet("font-family: monospace; font-size: 12px;")
        tabs.addTab(self.log, "Log")
        v.addWidget(tabs, 1)

        bar = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setFormat("")
        self.status = QLabel("Ready")
        self.status.setMinimumWidth(260)
        self.preview_btn = QPushButton("Render 30 s test")
        self.preview_btn.clicked.connect(lambda: self.start_render(test=True))
        self.render_btn = QPushButton("Render video")
        self.render_btn.setObjectName("primary")
        self.render_btn.clicked.connect(lambda: self.start_render(test=False))
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_render)
        self.open_btn = QPushButton("Open folder")
        self.open_btn.clicked.connect(self.open_output_folder)
        bar.addWidget(self.progress, 1)
        bar.addWidget(self.status)
        for b in (self.preview_btn, self.render_btn, self.cancel_btn, self.open_btn):
            bar.addWidget(b)
        v.addLayout(bar)
        return right

    # ---- job <-> widgets ------------------------------------------------------------------

    def collect(self):
        job = copy.deepcopy(DEFAULTS)
        job["quran_video"] = self.quran_edit.text().strip() or None
        meta = {k: e.text().strip() for k, e in self.meta_edits.items() if e.text().strip()}
        if meta.get("surah_number", "").isdigit():
            meta["surah_number"] = int(meta["surah_number"])
        job["meta"] = meta
        job["intro_seconds"] = self.intro.value()
        job["outro_seconds"] = self.outro.value()
        job["quran_layer"].update(key=self.key_combo.currentData(), key_color=self._key_color,
                                  similarity=self.similarity.value())
        job["backgrounds"].update(folder=self.bg_edit.text().strip() or None,
                                  max_clip_seconds=self.max_clip.value(),
                                  dim=self.dim.value() / 100, blur=self.blur.value(),
                                  random_start=self.random_start.isChecked())
        types = [self.trans_list.item(i).text() for i in range(self.trans_list.count())
                 if self.trans_list.item(i).checkState() == Qt.CheckState.Checked]
        job["transitions"].update(duration=self.trans_dur.value(), types=types or ["fade"],
                                  order=self.trans_order.currentData())
        job["cards"] = copy.deepcopy(self.cards)
        name = self.out_name.text().strip() or "{surah_en} - {reciter}"
        job["output"] = os.path.join(self.out_dir.text().strip() or os.path.expanduser("~/Videos"),
                                     name + ".mp4")
        w, h = self.resolution.currentData()
        job["video"].update(width=w, height=h, fps=self.fps.currentData(),
                            encoder=self.encoder.currentData(), quality=self.quality.value(),
                            preset=self.preset.currentData(), threads=self.threads.value())
        return job

    def apply(self, job):
        self._loading = True
        self.quran_edit.setText(job["quran_video"] or "")
        for k, e in self.meta_edits.items():
            e.setText(str(job["meta"].get(k, "")))
        self.surah_combo.setCurrentIndex(0)
        self.intro.setValue(job["intro_seconds"])
        self.outro.setValue(job["outro_seconds"])
        q = job["quran_layer"]
        self.key_combo.setCurrentIndex(max(0, self.key_combo.findData(q["key"])))
        self._set_key_color(q["key_color"])
        self.similarity.setValue(q["similarity"])
        b = job["backgrounds"]
        self.bg_edit.setText(b["folder"] or "")
        self.max_clip.setValue(b["max_clip_seconds"])
        self.dim.setValue(round(b["dim"] * 100))
        self.dim_label.setText(f"{self.dim.value()}%")
        self.blur.setValue(b["blur"])
        self.random_start.setChecked(b["random_start"])
        t = job["transitions"]
        self.trans_dur.setValue(t["duration"])
        self.trans_order.setCurrentIndex(max(0, self.trans_order.findData(t["order"])))
        for i in range(self.trans_list.count()):
            item = self.trans_list.item(i)
            item.setCheckState(Qt.CheckState.Checked if item.text() in t["types"]
                               else Qt.CheckState.Unchecked)
        self.cards = copy.deepcopy(job["cards"])
        folder, name = os.path.split(job["output"])
        self.out_dir.setText(folder or os.path.expanduser("~/Videos"))
        self.out_name.setText(os.path.splitext(name)[0])
        v = job["video"]
        self.resolution.setCurrentIndex(max(0, self.resolution.findData((v["width"], v["height"]))))
        self.fps.setCurrentIndex(max(0, self.fps.findData(v["fps"])))
        if self.encoder.findData(v["encoder"]) < 0:
            self.encoder.addItem(v["encoder"], v["encoder"])
        self.encoder.setCurrentIndex(self.encoder.findData(v["encoder"]))
        self.quality.setValue(int(v["quality"]))
        self.preset.setCurrentIndex(max(0, self.preset.findData(v["preset"])))
        self.threads.setValue(int(v["threads"]))
        self._loading = False

        self._refresh_card_list(0 if self.cards else -1)
        self._update_visibility()
        self.on_quran_changed()
        self.on_bg_changed()

    # ---- cards ----------------------------------------------------------------------------

    def _card_label(self, card):
        start = card.get("start", 0)
        when = f"{start:g}s" if start >= 0 else f"{-start:g}s before end"
        return f"{TEMPLATE_NAMES.get(card['template'], card['template'])}   ·   {when}, {card.get('duration', 6):g}s"

    def _refresh_card_list(self, select):
        self.card_list.blockSignals(True)
        self.card_list.clear()
        for card in self.cards:
            self.card_list.addItem(self._card_label(card))
        self.card_list.blockSignals(False)
        self.card_list.setCurrentRow(select)
        self.on_card_selected(select)

    def on_card_selected(self, row):
        self.card_form.setEnabled(0 <= row < len(self.cards))
        if not 0 <= row < len(self.cards):
            return
        card = self.cards[row]
        opts = card.get("options", {})
        self._loading = True
        self.c_template.setCurrentIndex(max(0, self.c_template.findData(card["template"])))
        self.c_start.setValue(card.get("start", 0))
        self.c_duration.setValue(card.get("duration", 6))
        self.c_fade.setValue(card.get("fade", 0.8))
        self.c_anim.setCurrentIndex(max(0, self.c_anim.findData(card.get("animation", "rise"))))
        self._set_accent(opts.get("accent", "#E3B85C"))
        self.c_backdrop.setValue(round(opts.get("backdrop", 0.5) * 100))
        self.c_position.setCurrentIndex(max(0, self.c_position.findData(opts.get("position", "top"))))
        self.c_translation.setChecked(card.get("fields", {}).get("translation", None) != "")
        self._loading = False
        self._update_visibility()
        # jump the preview into the middle of the card
        start = card.get("start", 0)
        if start < 0:
            start += self._total_seconds()
        self._want_time = int((start + min(card.get("duration", 6) / 2, 2.5)) * 10)
        self.time_slider.setValue(self._want_time)

    def store_card(self, *_):
        row = self.card_list.currentRow()
        if self._loading or not 0 <= row < len(self.cards):
            return
        card = self.cards[row]
        card.update(template=self.c_template.currentData(), start=self.c_start.value(),
                    duration=self.c_duration.value(), fade=self.c_fade.value(),
                    animation=self.c_anim.currentData())
        opts = card.setdefault("options", {})
        opts.update(accent=self._accent, backdrop=self.c_backdrop.value() / 100)
        if card["template"] == "corner":
            opts["position"] = self.c_position.currentData()
        fields = card.setdefault("fields", {})
        if self.c_translation.isChecked():
            fields.pop("translation", None)
        else:
            fields["translation"] = ""
        if not fields:
            card.pop("fields")
        self.card_list.item(row).setText(self._card_label(card))

    def add_card(self):
        card = copy.deepcopy(NEW_CARD)
        if self.cards:
            last = self.cards[-1]
            card["start"] = max(0, last.get("start", 0)) + last.get("duration", 6)
        self.cards.append(card)
        self._refresh_card_list(len(self.cards) - 1)
        self.changed()

    def remove_card(self):
        row = self.card_list.currentRow()
        if 0 <= row < len(self.cards):
            del self.cards[row]
            self._refresh_card_list(min(row, len(self.cards) - 1))
            self.changed()

    def _update_visibility(self, *_):
        chroma = self.key_combo.currentData() == "chromakey"
        self.key_row_label.setVisible(chroma)
        self.key_color_btn.parentWidget().setVisible(chroma)
        template = self.c_template.currentData() or ""
        self.c_position.setVisible(template == "corner")
        self.c_position_label.setVisible(template == "corner")
        self.c_translation.setVisible(template.startswith("bismillah"))

    # ---- colours ---------------------------------------------------------------------------

    def _swatch(self, button, hex_color):
        button.setText(hex_color.upper())
        text = "#111" if QColor(hex_color).lightness() > 140 else "#eee"
        button.setStyleSheet(f"background:{hex_color}; color:{text}; border-radius:5px; padding:4px 10px;")

    def _set_accent(self, hex_color):
        self._accent = hex_color
        self._swatch(self.c_accent, hex_color)

    def _set_key_color(self, value):
        self._key_color = value
        self._swatch(self.key_color_btn, "#" + value[2:] if value.startswith("0x") else value)

    def pick_accent(self):
        c = QColorDialog.getColor(QColor(self._accent), self, "Accent colour")
        if c.isValid():
            self._set_accent(c.name())
            self.store_card()
            self.changed()

    def pick_key_color(self):
        c = QColorDialog.getColor(QColor("#" + self._key_color[2:]), self, "Key colour")
        if c.isValid():
            self._set_key_color("0x" + c.name()[1:].upper())
            self.changed()

    # ---- inputs ----------------------------------------------------------------------------

    def browse_quran(self):
        start = os.path.dirname(self.quran_edit.text()) or self.settings.value("dir_quran", "")
        path, _ = QFileDialog.getOpenFileName(self, "Recitation video", start, VIDEO_FILTER)
        if path:
            self.settings.setValue("dir_quran", os.path.dirname(path))
            self.quran_edit.setText(path)
            self.on_quran_changed()

    def browse_bg(self):
        path = QFileDialog.getExistingDirectory(self, "Background clip folder", self.bg_edit.text())
        if path:
            self.bg_edit.setText(path)
            self.on_bg_changed()

    def browse_out(self):
        path = QFileDialog.getExistingDirectory(self, "Output folder", self.out_dir.text())
        if path:
            self.out_dir.setText(path)

    def on_quran_changed(self):
        path = self.quran_edit.text().strip()
        # editingFinished also fires when focus just leaves the box; only reload a new path
        if self._loaded_paths.get("quran") == path:
            return
        self._loaded_paths["quran"] = path
        self.quran_info = None
        self.quran_info_label.setText("")
        if path and os.path.isfile(path):
            self.quran_info_label.setText("Reading video…")
            self._start(Task(("quran", path), probe_video, path))
        self._update_timeline()

    def on_bg_changed(self):
        folder = self.bg_edit.text().strip()
        if self._loaded_paths.get("bg") == folder:
            return
        self._loaded_paths["bg"] = folder
        self.clips, self.bg_clip = [], None
        self.bg_info.setText("")
        if folder and os.path.isdir(folder):
            self.bg_info.setText("Scanning clips… (first time can take a while)")
            self._start(Task(("bg", folder), scan_folder, folder))
        self.changed()

    def on_surah_picked(self, index):
        data = self.surah_combo.itemData(index)
        if not data:
            return
        n, en, ar, meaning = data
        self.meta_edits["surah_number"].setText(str(n))
        self.meta_edits["surah_en"].setText(f"Surah {en}")
        self.meta_edits["surah_ar"].setText(f"سورة {ar}")
        self.meta_edits["surah_meaning"].setText(meaning)

    def shuffle_clip(self):
        if len(self.clips) > 1:
            self.bg_clip = random.choice([c for c in self.clips if c != self.bg_clip])
            self.changed()

    # ---- preview ---------------------------------------------------------------------------

    def _total_seconds(self):
        q = self.quran_info["duration"] if self.quran_info else 0
        return self.intro.value() + q + self.outro.value()

    def _update_timeline(self):
        total = self._total_seconds()
        self.time_slider.setMaximum(max(0, int(total * 10) - 1))
        if self._want_time is not None and self.time_slider.maximum() >= self._want_time:
            self.time_slider.setValue(self._want_time)
            self._want_time = None
        self.on_time_changed(self.time_slider.value())

    def on_time_changed(self, value):
        self.time_label.setText(f"{fmt_time(value / 10)} / {fmt_time(self._total_seconds())}")
        if not self._loading:
            self.preview_timer.start()

    def changed(self, *_):
        if self._loading:
            return
        if self.sender() in (self.intro, self.outro):
            self._update_timeline()
        self.preview_timer.start()

    def refresh_preview(self):
        job = self.collect()
        if not job["quran_video"] and not self.bg_clip and not job["cards"]:
            return
        self._preview_gen += 1
        q_dur = self.quran_info["duration"] if self.quran_info else 0
        if not self.quran_info:
            job["quran_video"] = None
        self._start(Task(("preview", self._preview_gen), make_preview, job,
                         self.time_slider.value() / 10, self.bg_clip, q_dur, PREVIEW_SIZE))

    # ---- background tasks ------------------------------------------------------------------

    def _start(self, task):
        task.signals.result.connect(self.on_task_result)
        task.signals.failed.connect(self.on_task_failed)
        self.pool.start(task)

    def on_task_result(self, tag, value):
        kind = tag[0] if isinstance(tag, tuple) else tag
        if kind == "preview":
            if tag[1] == self._preview_gen:
                self.preview.set_image(value)
        elif kind == "quran" and tag[1] == self.quran_edit.text().strip():
            self.quran_info = value
            self.quran_info_label.setText(
                f"{fmt_time(value['duration'])}  ·  {value['width']}×{value['height']}  ·  "
                f"{value['fps']:g} fps" + ("" if value["has_audio"] else "  ·  no audio"))
            self._update_timeline()
        elif kind == "bg" and tag[1] == self.bg_edit.text().strip():
            self.clips, total = value
            self.bg_info.setText(f"{len(self.clips)} clips  ·  {total / 60:.0f} min of footage"
                                 if self.clips else "No video clips found in this folder")
            self.bg_clip = random.choice(self.clips) if self.clips else None
            self.changed()
        elif kind == "encoders":
            names = {"h264_nvenc": "NVIDIA GPU (NVENC)", "h264_qsv": "Intel GPU (Quick Sync)",
                     "h264_amf": "AMD GPU (AMF)"}
            for enc in value:
                if self.encoder.findData(enc) < 0:
                    self.encoder.addItem(names.get(enc, enc), enc)

    def on_task_failed(self, tag, message):
        kind = tag[0] if isinstance(tag, tuple) else tag
        if kind == "quran":
            self.quran_info_label.setText("Could not read this video")
        elif kind == "bg":
            self.bg_info.setText(f"Could not scan folder: {message}")
        elif kind == "preview":
            self.preview.setText(f"Preview failed: {message}")

    # ---- rendering -------------------------------------------------------------------------

    def start_render(self, test):
        job = self.collect()
        problems = []
        if not job["quran_video"] or not os.path.isfile(job["quran_video"]):
            problems.append("Choose the recitation video.")
        if not job["backgrounds"]["folder"] or not self.clips:
            problems.append("Choose a folder that has background clips.")
        if problems:
            QMessageBox.warning(self, "Missing", "\n".join(problems))
            return
        try:
            job = prepare_job(job, os.getcwd())
        except Exception as exc:
            QMessageBox.warning(self, "Settings", str(exc))
            return
        if test:
            stem, ext = os.path.splitext(job["output"])
            job["output"] = f"{stem} (test){ext}"
        elif os.path.exists(job["output"]):
            answer = QMessageBox.question(self, "Replace?",
                                          f"{os.path.basename(job['output'])} already exists. Replace it?")
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._save_last()
        self.log.appendPlainText(f"\n=== {os.path.basename(job['output'])} ===")
        self.render_thread = RenderThread(job, 30 if test else None)
        self.render_thread.progress.connect(self.on_progress)
        self.render_thread.line.connect(self.log.appendPlainText)
        self.render_thread.done.connect(self.on_render_done)
        thread = self.render_thread
        self._threads.add(thread)
        thread.finished.connect(lambda: self._threads.discard(thread))
        self._set_rendering(True)
        self.status.setText("Preparing…")
        self.progress.setValue(0)
        self.render_thread.start()

    def _set_rendering(self, busy):
        self.render_btn.setEnabled(not busy)
        self.preview_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        self.progress.setFormat("%p%" if busy else "")

    def on_progress(self, fraction, speed, eta):
        self.progress.setValue(int(fraction * 1000))
        self.status.setText(f"{speed:.1f}× real time  ·  {fmt_time(eta)} left")

    def cancel_render(self):
        if self.render_thread:
            self.status.setText("Stopping…")
            self.render_thread.stop()

    def on_render_done(self, ok, message):
        self._set_rendering(False)
        self.render_thread = None
        if ok:
            self.progress.setValue(1000)
            self.status.setText("Done")
            self.last_output = message
            self.log.appendPlainText(f"Saved: {message}")
            if "(test)" in os.path.basename(message):
                QDesktopServices.openUrl(QUrl.fromLocalFile(message))
        else:
            self.status.setText("Stopped" if message.startswith("Cancelled") else "Failed — see Log")
            self.log.appendPlainText(message)

    def open_output_folder(self):
        folder = self.out_dir.text().strip()
        if folder and os.path.isdir(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    # ---- project files ---------------------------------------------------------------------

    def new_project(self):
        job = copy.deepcopy(DEFAULTS)
        current = self.collect()
        # keep the things that rarely change between videos
        job["backgrounds"]["folder"] = current["backgrounds"]["folder"]
        job["meta"]["channel"] = current["meta"].get("channel", "")
        job["output"] = current["output"]
        self.project_path = None
        self.apply(job)

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open project", self.settings.value("dir_project", ""),
                                              "Project (*.json)")
        if path:
            self.open_path(path)

    def open_path(self, path):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Open project", str(exc))
            return
        if "jobs" in data:
            data = deep_merge(data.get("defaults", {}), data["jobs"][0] if data["jobs"] else {})
            QMessageBox.information(self, "Batch file", "This is a batch file; the first job was opened. "
                                    "Render whole batches with:  python -m qve render file.json")
        base = os.path.dirname(path)
        job = deep_merge(DEFAULTS, data)
        for holder, key in ((job, "quran_video"), (job["backgrounds"], "folder"), (job, "output")):
            if holder[key] and not os.path.isabs(holder[key]):
                holder[key] = os.path.normpath(os.path.join(base, holder[key]))
        self.project_path = path
        self.settings.setValue("dir_project", base)
        self.apply(job)
        self.setWindowTitle(f"Quran Video Editor — {os.path.basename(path)}")

    def save_project(self, ask=False):
        path = self.project_path
        if ask or not path:
            path, _ = QFileDialog.getSaveFileName(self, "Save project", self.settings.value("dir_project", ""),
                                                  "Project (*.json)")
            if not path:
                return
            if not path.endswith(".json"):
                path += ".json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.collect(), fh, ensure_ascii=False, indent=2)
        self.project_path = path
        self.settings.setValue("dir_project", os.path.dirname(path))
        self.setWindowTitle(f"Quran Video Editor — {os.path.basename(path)}")

    def _save_last(self):
        self.settings.setValue("last_job", json.dumps(self.collect(), ensure_ascii=False))

    def closeEvent(self, event):
        if self.render_thread:
            answer = QMessageBox.question(self, "Rendering", "A render is running. Stop it and quit?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.render_thread.stop()
            self.render_thread.wait(5000)
        self._save_last()
        self.settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(event)
