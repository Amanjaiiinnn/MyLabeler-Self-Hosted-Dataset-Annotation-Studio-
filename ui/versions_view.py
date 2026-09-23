"""
ui/versions_view.py — build a trainable dataset out of the project.

Two ordered steps, because the order genuinely matters: preprocessing changes
pixels and labels, augmentation multiplies them, then export splits and writes
them. Existing versions are listed on the left with what they actually contain.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame, QGridLayout,
)

from core.dataset import PreprocessConfig
from ui.theme import T
from ui.widgets import (
    Toolbar, StatusBar, Card, Banner, Meter, button, ghost_button,
    primary_button, line_edit, mono_label, vrule, spin, check,
)
from ui.preprocessing_dialog import PreprocessingDialog

# key -> (title, what it actually does at export time)
STEP_LIBRARY: Dict[str, Tuple[str, str]] = {
    "resize":        ("Resize", "Letterbox to 640×640, aspect preserved"),
    "grayscale":     ("Grayscale", "Convert to single channel, stored as 3-channel"),
    "contrast":      ("Auto-contrast", "CLAHE equalisation on the luminance channel"),
    "filter_null":   ("Filter null", "Drop images that have no boxes"),
    "random_sample": ("Random sample", "Keep a random 50% of the images"),
}


class StepRow(QFrame):
    """One configured preprocessing step. Ordered, removable."""
    removeClicked = Signal(str)

    def __init__(self, index: int, key: str, title: str, detail: str, parent=None):
        super().__init__(parent)
        self.setObjectName("StepRow")
        self.key = key
        self.setStyleSheet(
            f"QFrame#StepRow{{background:{T.INK_800};border:1px solid {T.LINE};"
            f"border-radius:{T.R_SM}px;}}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(T.S3, T.S2, T.S2, T.S2)
        lay.setSpacing(T.S3)

        n = mono_label(str(index), T.FS_SMALL, T.TX_4)
        n.setFixedWidth(12)
        n.setStyleSheet(f"color:{T.TX_4};background:transparent;border:none;")
        lay.addWidget(n)

        col = QVBoxLayout()
        col.setSpacing(0)
        t = QLabel(title)
        t.setStyleSheet(f"color:{T.TX_1};font-size:{T.FS_CONTROL}px;font-weight:600;"
                        f"background:transparent;border:none;")
        d = QLabel(detail)
        d.setStyleSheet(f"color:{T.TX_3};font-size:{T.FS_SMALL}px;"
                        f"background:transparent;border:none;")
        col.addWidget(t)
        col.addWidget(d)
        lay.addLayout(col, stretch=1)

        rm = ghost_button("", "Remove this step", "minus", "sm")
        rm.setFixedWidth(30)
        rm.clicked.connect(lambda: self.removeClicked.emit(self.key))
        lay.addWidget(rm)


class VersionsView(QWidget):
    labelImagesRequested = Signal()
    generateAugmentationsRequested = Signal()
    exportDatasetRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.pm = None
        self._steps: List[str] = ["resize"]

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        tb = Toolbar("Versions")
        tb.set_subtitle("preprocess, augment, export")
        self.btn_label = ghost_button(
            "Auto-label first", "Label everything that has no boxes yet", "play", "sm")
        self.btn_label.clicked.connect(self.labelImagesRequested)
        self.btn_export = primary_button(
            "Create version", "Build train/val and write data.yaml", "box", "sm")
        self.btn_export.clicked.connect(self.exportDatasetRequested)
        tb.add(self.btn_label, vrule(), self.btn_export)
        root.addWidget(tb)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_version_list())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("Page")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(T.S6, T.S5, T.S6, T.S5)
        lay.setSpacing(T.S4)

        name_card = Card("Version name")
        self.vname_edit = line_edit("", f"v{datetime.now().strftime('%Y%m%d_%H%M')}")
        name_card.body.addWidget(self.vname_edit)
        lay.addWidget(name_card)

        lay.addWidget(self._build_split_card())
        lay.addWidget(self._build_step_card())
        lay.addWidget(self._build_augment_card())
        lay.addWidget(Banner(
            "The split is computed over original images only; each image's "
            "augmented copies follow it into the same split. That is what keeps a "
            "near-duplicate of a training photo out of validation.",
            "info", "check"))
        lay.addStretch()

        scroll.setWidget(content)
        body.addWidget(scroll, stretch=1)
        root.addLayout(body, stretch=1)

        self.status = StatusBar()
        root.addWidget(self.status)
        self._render_steps()

    # -------------------------------------------------------------- panels
    def _build_version_list(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("Rail")
        panel.setFixedWidth(230)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(T.S3, T.S3, T.S3, T.S3)
        lay.setSpacing(T.S2)
        cap = QLabel("EXISTING VERSIONS")
        cap.setObjectName("SectionLabel")
        lay.addWidget(cap)
        self.version_box = QVBoxLayout()
        self.version_box.setSpacing(T.S1)
        lay.addLayout(self.version_box)
        lay.addStretch()
        return panel

    def _build_split_card(self) -> Card:
        """Configure train / valid / test before anything is generated."""
        card = Card("Step 1 — Train / Test split",
                    "decides which images the model never sees during training")

        self.split_rows = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(T.S3)
        grid.setVerticalSpacing(T.S2)
        for row, (key, label, default, color) in enumerate((
                ("train", "Train", 70, T.ACCENT),
                ("valid", "Valid", 20, T.OK),
                ("test", "Test", 10, T.WARN))):
            name = QLabel(label)
            name.setStyleSheet(f"color:{T.TX_1};font-size:{T.FS_CONTROL}px;")
            name.setFixedWidth(52)
            sp = spin(0, 100, default, " %", width=84)
            sp.valueChanged.connect(lambda _=0: self._update_split_preview())
            meter = Meter(color, default / 100)
            now = mono_label("", T.FS_SMALL, T.TX_2)
            now.setFixedWidth(150)
            now.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(name, row, 0)
            grid.addWidget(sp, row, 1)
            grid.addWidget(meter, row, 2)
            grid.addWidget(now, row, 3)
            grid.setColumnStretch(2, 1)
            self.split_rows[key] = (sp, meter, now)
        card.body.addLayout(grid)

        controls = QHBoxLayout()
        controls.setSpacing(T.S3)
        self.split_only_chk = check("Only images with no split yet")
        self.split_only_chk.setToolTip(
            "Leave anything you placed by hand on the Dataset page alone")
        self.split_only_chk.toggled.connect(lambda _: self._update_split_preview())
        controls.addWidget(self.split_only_chk)
        controls.addStretch()
        seed_lbl = QLabel("Seed")
        seed_lbl.setObjectName("Muted")
        controls.addWidget(seed_lbl)
        self.split_seed = spin(0, 999999, 42, width=86)
        self.split_seed.setToolTip("Same seed reproduces the same split")
        controls.addWidget(self.split_seed)
        self.btn_apply_split = button("Apply split", "Deal images into the ratios above",
                                      "layers", "sm")
        self.btn_apply_split.clicked.connect(self._apply_split)
        controls.addWidget(self.btn_apply_split)
        card.body.addLayout(controls)

        self.split_note = Banner("", "info", "check")
        card.body.addWidget(self.split_note)
        return card

    def _update_split_preview(self):
        if not self.pm:
            return
        counts = self.pm.split_counts()
        ratios = {k: self.split_rows[k][0].value() for k in self.split_rows}
        total_ratio = sum(ratios.values())
        pool = counts["default"] if self.split_only_chk.isChecked() else counts["all"]

        for key, (sp, meter, now) in self.split_rows.items():
            meter.set_fraction((sp.value() / total_ratio) if total_ratio else 0)
            projected = (int(round(pool * sp.value() / total_ratio))
                         if total_ratio else 0)
            now.setText(f"now {counts[key]:,}  →  {projected:,}")

        self.btn_apply_split.setEnabled(total_ratio > 0 and pool > 0)
        if total_ratio <= 0:
            self.split_note.set_text("Ratios add up to zero — nothing to deal.")
        elif pool == 0:
            self.split_note.set_text(
                "Every image already has a split. Untick the box above to "
                "reshuffle them all.")
        else:
            extra = ("" if total_ratio == 100
                     else f" Ratios total {total_ratio}, so they are scaled to fit.")
            self.split_note.set_text(
                f"<b>{pool:,}</b> image(s) will be dealt out.{extra} "
                f"Unassigned images left over at export time fall back to the "
                f"validation percentage in the export dialog.")

    def _apply_split(self):
        if not self.pm:
            return
        r = {k: float(self.split_rows[k][0].value()) for k in self.split_rows}
        res = self.pm.rebalance_splits(
            train=r["train"], valid=r["valid"], test=r["test"],
            seed=self.split_seed.value(),
            only_unassigned=self.split_only_chk.isChecked())
        self.refresh()
        self.status.set_left(
            f"split applied — train {res['train']:,} · valid {res['valid']:,} "
            f"· test {res['test']:,}", T.OK)

    def _build_step_card(self) -> Card:
        card = Card("Step 2 — Preprocessing",
                    "applied to every image as it is written out")
        self.steps_box = QVBoxLayout()
        self.steps_box.setSpacing(T.S2)
        card.body.addLayout(self.steps_box)
        self.add_step_btn = ghost_button("Add step", icon_name="plus")
        self.add_step_btn.clicked.connect(self._open_step_dialog)
        card.body.addWidget(self.add_step_btn, alignment=Qt.AlignLeft)
        return card

    def _build_augment_card(self) -> Card:
        card = Card("Step 3 — Augmentation", "generates extra training copies")
        desc = QLabel(
            "Flips, rotation, shear, blur, colour shift, noise and cutout. "
            "OBB/polygon labels are carried through as points, so rotation is "
            "preserved rather than flattened to an upright box.")
        desc.setWordWrap(True)
        desc.setObjectName("Body")
        card.body.addWidget(desc)
        btn = button("Configure augmentations…", icon_name="sliders")
        btn.clicked.connect(self.generateAugmentationsRequested)
        card.body.addWidget(btn, alignment=Qt.AlignLeft)
        return card

    # --------------------------------------------------------------- steps
    def _render_steps(self):
        while self.steps_box.count():
            w = self.steps_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not self._steps:
            empty = QLabel("No preprocessing — images are exported as they are.")
            empty.setObjectName("Muted")
            self.steps_box.addWidget(empty)
            return
        for i, key in enumerate(self._steps, 1):
            title, detail = STEP_LIBRARY[key]
            row = StepRow(i, key, title, detail)
            row.removeClicked.connect(self._remove_step)
            self.steps_box.addWidget(row)

    def _remove_step(self, key: str):
        self._steps = [k for k in self._steps if k != key]
        self._render_steps()

    def _open_step_dialog(self):
        dlg = PreprocessingDialog(self, already=set(self._steps))
        if not dlg.exec():
            return
        key = dlg.chosen_step
        if key in STEP_LIBRARY and key not in self._steps:
            self._steps.append(key)
            self._render_steps()

    def preprocess_config(self) -> PreprocessConfig:
        keys = set(self._steps)
        return PreprocessConfig(
            resize=(640, 640) if "resize" in keys else None,
            grayscale="grayscale" in keys,
            auto_contrast="contrast" in keys,
            filter_null="filter_null" in keys,
            random_sample_percent=50 if "random_sample" in keys else 100,
        )

    def version_name(self) -> str:
        return self.vname_edit.text().strip()

    # ---------------------------------------------------------------- data
    def set_project(self, pm):
        self.pm = pm
        self.refresh()

    def refresh(self):
        while self.version_box.count():
            w = self.version_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not self.pm:
            self.status.set_left("no project")
            return

        exports = []
        if self.pm.exports_dir.exists():
            exports = sorted((p for p in self.pm.exports_dir.iterdir() if p.is_dir()),
                             key=lambda p: p.stat().st_mtime, reverse=True)
        if not exports:
            empty = QLabel("No versions yet.")
            empty.setObjectName("Muted")
            empty.setWordWrap(True)
            self.version_box.addWidget(empty)
        else:
            for p in exports:
                self.version_box.addWidget(self._version_row(p))

        stats = self.pm.stats()
        labeled = stats["labeled"] + stats["auto-labeled"]
        self.status.set_left(
            f"{labeled:,} of {stats['total']:,} images have boxes",
            T.WARN if labeled < stats["total"] else T.TX_3)
        self._update_split_preview()
        n_aug = 0
        if self.pm.aug_images_dir.exists():
            n_aug = sum(1 for _ in self.pm.aug_images_dir.glob("*"))
        self.status.set_right(f"{n_aug:,} augmented · {len(exports)} version(s)")

    def _version_row(self, path: Path) -> QWidget:
        try:
            n_train = len(list((path / "train" / "images").iterdir()))
            n_val = len(list((path / "val" / "images").iterdir()))
        except OSError:
            n_train = n_val = 0
        w = QFrame()
        w.setStyleSheet(
            f"QFrame#StepRow{{background:{T.INK_800};border:1px solid {T.LINE};"
            f"border-radius:{T.R_SM}px;}}")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(T.S3, T.S2, T.S3, T.S2)
        lay.setSpacing(1)
        name = QLabel(path.name)
        name.setStyleSheet(f"color:{T.TX_1};font-size:{T.FS_CONTROL}px;"
                           f"font-weight:600;background:transparent;border:none;")
        name.setToolTip(str(path))
        meta = mono_label(f"{n_train:,} train · {n_val:,} val", T.FS_SMALL, T.TX_3)
        meta.setStyleSheet(f"color:{T.TX_3};background:transparent;border:none;")
        lay.addWidget(name)
        lay.addWidget(meta)
        return w
