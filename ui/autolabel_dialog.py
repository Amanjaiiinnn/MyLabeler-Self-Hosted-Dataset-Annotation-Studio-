"""
ui/autolabel_dialog.py — choose the model, choose what to label, name it yourself.

Pick weights here and the full class list of that model appears; tick any number
of them and type the name each should carry in your dataset. Only ticked classes
are predicted, so a COCO model can be used to label just the two things you care
about.

Names you type are written into the project's class table against the model's
own class id, so the id in the label file and the name in data.yaml agree.
"""
from __future__ import annotations
from typing import Dict, List, Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QWidget, QFrame,
    QDialogButtonBox, QDoubleSpinBox,
)

from ui.theme import T, mono_font, class_color
from ui.icons import icon, swatch
from ui.widgets import (
    Banner, button, ghost_button, primary_button, line_edit, mono_label,
    check, hrule,
)


class ClassRow(QWidget):
    """One model class: tick it, and name it whatever you want."""
    toggled = Signal()

    def __init__(self, class_id: int, model_name: str, project_name: str = "",
                 checked: bool = False, parent=None):
        super().__init__(parent)
        self.class_id = class_id
        self.model_name = model_name
        self.filtered_out = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(T.S2, 3, T.S2, 3)
        lay.setSpacing(T.S3)

        self.chk = check("")
        self.chk.setChecked(checked)
        self.chk.setFixedWidth(20)
        self.chk.toggled.connect(self._on_toggle)
        lay.addWidget(self.chk)

        sw = QLabel()
        sw.setPixmap(swatch(class_color(class_id), 10, 3).pixmap(10, 10))
        sw.setFixedWidth(12)
        lay.addWidget(sw)

        id_lbl = mono_label(f"{class_id:>3}", T.FS_SMALL, T.TX_4)
        id_lbl.setFixedWidth(26)
        lay.addWidget(id_lbl)

        self.model_lbl = QLabel(model_name)
        self.model_lbl.setFixedWidth(168)
        lay.addWidget(self.model_lbl)

        arrow = QLabel()
        arrow.setPixmap(icon("arrow", T.TX_4, 13).pixmap(13, 13))
        arrow.setFixedWidth(15)
        lay.addWidget(arrow)

        self.name_edit = line_edit(model_name, project_name or model_name)
        self.name_edit.setToolTip(
            "The name this class gets in your dataset and in data.yaml")
        lay.addWidget(self.name_edit, stretch=1)

        self._sync_enabled()

    def _on_toggle(self, _):
        self._sync_enabled()
        self.toggled.emit()

    def _sync_enabled(self):
        on = self.chk.isChecked()
        self.name_edit.setEnabled(on)
        self.model_lbl.setStyleSheet(
            f"color:{T.TX_1 if on else T.TX_3};font-size:{T.FS_CONTROL}px;"
            f"font-weight:{'600' if on else '400'};background:transparent;")

    @property
    def selected(self) -> bool:
        return self.chk.isChecked()

    @property
    def label_name(self) -> str:
        return self.name_edit.text().strip() or self.model_name


class AutoLabelDialog(QDialog):
    """
    Emits modelChangeRequested when the user wants different weights; the caller
    loads them and calls set_model() / set_model_failed().

    Results after exec():
        .selected_ids   list[int]        model class ids to detect
        .class_names    dict[int, str]   id -> the name you typed
        .confidence     float
        .overwrite      bool
    """

    modelChangeRequested = Signal()

    def __init__(self, parent=None, model_name: str = "",
                 model_classes: Optional[Sequence[str]] = None,
                 project_classes: Optional[Dict[int, str]] = None,
                 confidence: float = 0.25, image_count: int = 0,
                 preselected: Optional[Sequence[int]] = None,
                 preset_names: Optional[Dict[int, str]] = None):
        super().__init__(parent)
        self.setWindowTitle("Auto-label")
        self.setMinimumSize(700, 640)

        self.selected_ids: List[int] = []
        self.class_names: Dict[int, str] = {}
        self.confidence = confidence
        self.overwrite = False

        self._project_classes = dict(project_classes or {})
        self._preselected = set(preselected or [])
        self._preset_names = dict(preset_names or {})
        self._image_count = image_count
        self._rows: List[ClassRow] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(T.S5, T.S4, T.S5, T.S4)
        lay.setSpacing(T.S3)

        head = QLabel("Auto-label")
        head.setObjectName("Display")
        lay.addWidget(head)

        # ── model row ─────────────────────────────────────────
        lay.addWidget(self._build_model_row())
        lay.addWidget(hrule())

        # ── controls row ──────────────────────────────────────
        controls = QHBoxLayout()
        controls.setSpacing(T.S2)
        self.search = line_edit("Filter classes…", width=200)
        self.search.textChanged.connect(self._apply_filter)
        controls.addWidget(self.search)

        self.btn_all = ghost_button("Select all", "Tick every class shown", size="sm")
        self.btn_all.clicked.connect(lambda: self._set_all(True))
        self.btn_none = ghost_button("Select none", size="sm")
        self.btn_none.clicked.connect(lambda: self._set_all(False))
        controls.addWidget(self.btn_all)
        controls.addWidget(self.btn_none)
        controls.addStretch()

        controls.addWidget(QLabel("Confidence"))
        self.conf_spin = QDoubleSpinBox()
        self.conf_spin.setRange(0.05, 0.95)
        self.conf_spin.setSingleStep(0.05)
        self.conf_spin.setValue(confidence)
        self.conf_spin.setFixedWidth(74)
        self.conf_spin.setFont(mono_font(T.FS_CONTROL))
        self.conf_spin.setToolTip("Detections scoring below this are discarded")
        controls.addWidget(self.conf_spin)
        lay.addLayout(controls)

        # ── column header ─────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setContentsMargins(T.S2 + 60, 0, T.S2, 0)
        hdr.setSpacing(T.S3)
        m = QLabel("MODEL CLASS")
        m.setObjectName("SectionLabel")
        m.setFixedWidth(184)
        n = QLabel("NAME IN YOUR DATASET")
        n.setObjectName("SectionLabel")
        hdr.addWidget(m)
        hdr.addWidget(n, stretch=1)
        lay.addLayout(hdr)

        # ── class list ────────────────────────────────────────
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet(
            f"QScrollArea{{background:{T.INK_850};border:1px solid {T.LINE};"
            f"border-radius:{T.R}px;}}")
        lay.addWidget(self.scroll, stretch=1)

        self.overwrite_chk = check("Replace labels on images that already have boxes")
        self.overwrite_chk.setToolTip(
            "Off: only images with no boxes are labelled.\n"
            "On: existing boxes are overwritten by the model's predictions.")
        lay.addWidget(self.overwrite_chk)

        self.summary = Banner("", "info", "check")
        lay.addWidget(self.summary)

        buttons = QDialogButtonBox()
        self.run_btn = primary_button("Run auto-label", icon_name="play")
        cancel_btn = button("Cancel")
        cancel_btn.clicked.connect(self.reject)
        self.run_btn.clicked.connect(self._on_accept)
        buttons.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        buttons.addButton(self.run_btn, QDialogButtonBox.AcceptRole)
        lay.addWidget(buttons)

        self.set_model(model_name, model_classes or [])

    # ------------------------------------------------------------ model row
    def _build_model_row(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("Card")
        row = QHBoxLayout(wrap)
        row.setContentsMargins(T.S3, T.S2 + 2, T.S3, T.S2 + 2)
        row.setSpacing(T.S3)

        glyph = QLabel()
        glyph.setPixmap(icon("brain", T.ACCENT, 16).pixmap(16, 16))
        glyph.setFixedSize(30, 30)
        glyph.setAlignment(Qt.AlignCenter)
        glyph.setStyleSheet(
            f"background:{T.ACCENT_WASH};border-radius:{T.R_SM}px;border:none;")
        row.addWidget(glyph)

        col = QVBoxLayout()
        col.setSpacing(1)
        self.model_name_lbl = QLabel("No model loaded")
        self.model_name_lbl.setStyleSheet(
            f"color:{T.TX_1};font-size:{T.FS_CONTROL}px;font-weight:600;"
            f"background:transparent;border:none;")
        self.model_meta_lbl = mono_label("choose weights to see its classes",
                                         T.FS_SMALL, T.TX_3)
        self.model_meta_lbl.setStyleSheet(
            f"color:{T.TX_3};background:transparent;border:none;")
        col.addWidget(self.model_name_lbl)
        col.addWidget(self.model_meta_lbl)
        row.addLayout(col, stretch=1)

        self.btn_model = button("Choose model…", "Load different .pt weights",
                                "folder", "sm")
        self.btn_model.clicked.connect(self.modelChangeRequested)
        row.addWidget(self.btn_model)
        return wrap

    def set_loading(self, name: str):
        self.model_name_lbl.setText(name)
        self.model_meta_lbl.setText("loading…")
        self.btn_model.setEnabled(False)
        self.run_btn.setEnabled(False)

    def set_model_failed(self, message: str):
        self.model_meta_lbl.setText("failed to load")
        self.model_meta_lbl.setStyleSheet(
            f"color:{T.DANGER_TEXT};background:transparent;border:none;")
        self.btn_model.setEnabled(True)
        self.summary.set_text(f"Could not load those weights: {message}")

    def set_model(self, name: str, classes: Sequence[str],
                  project_classes: Optional[Dict[int, str]] = None):
        """Show every class this model can detect, ready to be ticked."""
        if project_classes is not None:
            self._project_classes = dict(project_classes)
        classes = list(classes)
        self.btn_model.setEnabled(True)

        if name:
            self.model_name_lbl.setText(name)
            self.model_meta_lbl.setText(
                f"{len(classes)} class(es) available" if classes
                else "no classes reported")
            self.model_meta_lbl.setStyleSheet(
                f"color:{T.TX_3};background:transparent;border:none;")
        self._rebuild_rows(classes)

    def _rebuild_rows(self, classes: Sequence[str]):
        old = self.scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self._rows.clear()

        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.setAlignment(Qt.AlignTop)

        if not classes:
            empty = QLabel(
                "No model loaded yet.\n\n"
                "Choose weights above and every class the model can detect will "
                "be listed here for you to pick from.")
            empty.setObjectName("Muted")
            empty.setWordWrap(True)
            empty.setAlignment(Qt.AlignCenter)
            empty.setContentsMargins(T.S5, T.S6, T.S5, T.S6)
            lay.addWidget(empty)
        else:
            for cid, mname in enumerate(classes):
                preset = self._preset_names.get(cid) or self._project_classes.get(cid, "")
                row = ClassRow(cid, mname, preset, checked=(cid in self._preselected))
                row.toggled.connect(self._update_summary)
                self._rows.append(row)
                lay.addWidget(row)

        self.scroll.setWidget(inner)
        has = bool(classes)
        for w in (self.search, self.btn_all, self.btn_none):
            w.setEnabled(has)
        self.search.clear()
        self._update_summary()

    # ------------------------------------------------------------- helpers
    def _visible_rows(self) -> List[ClassRow]:
        """Rows the current search leaves showing.

        Tracked on the row rather than read from isVisible(), which reports
        False for every child until the dialog itself is shown.
        """
        return [r for r in self._rows if not r.filtered_out]

    def _set_all(self, on: bool):
        for row in self._visible_rows():
            row.chk.setChecked(on)
        self._update_summary()

    def _apply_filter(self, text: str):
        q = text.strip().lower()
        for row in self._rows:
            keep = (not q or q in row.model_name.lower()
                    or q in row.label_name.lower() or q == str(row.class_id))
            row.filtered_out = not keep
            row.setVisible(keep)
        if q and not self._visible_rows():
            self.summary.set_text(f"No model class matches “{text.strip()}”.")
        else:
            self._update_summary()

    def _update_summary(self):
        if not self._rows:
            self.summary.set_text(
                "Choose a model above to see the classes you can label.")
            self.run_btn.setEnabled(False)
            return
        chosen = [r for r in self._rows if r.selected]
        self.run_btn.setEnabled(bool(chosen))
        if not chosen:
            self.summary.set_text(
                f"Nothing selected. Tick any of the {len(self._rows)} class(es) "
                f"above — the rest are ignored entirely.")
            return
        names = ", ".join(r.label_name for r in chosen[:6])
        more = f" and {len(chosen) - 6} more" if len(chosen) > 6 else ""
        scope = (f"{self._image_count:,} image(s)" if self._image_count
                 else "the selected images")
        self.summary.set_text(
            f"Detecting <b>{len(chosen)}</b> of {len(self._rows)} class(es) "
            f"across {scope}: {names}{more}.")

    def _on_accept(self):
        chosen = [r for r in self._rows if r.selected]
        if not chosen:
            return
        self.selected_ids = [r.class_id for r in chosen]
        self.class_names = {r.class_id: r.label_name for r in chosen}
        self.confidence = self.conf_spin.value()
        self.overwrite = self.overwrite_chk.isChecked()
        self.accept()
