"""
ui/dataset_view.py — the gallery.

Status reads from the corner of every card rather than from a legend, so an
unreviewed auto-label pass is visible at a glance. Selecting images turns the
toolbar into a batch bar instead of floating a second bar over the grid.

The model controls live here (and on Annotate) rather than in a global header:
this is the page where auto-labelling actually happens.
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional, Set

from PySide6.QtCore import Signal, Qt, QRectF, QTimer
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QBrush, QPolygonF
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QCheckBox, QFrame, QScrollArea, QMessageBox, QDoubleSpinBox, QSizePolicy,
)

from core.annotation import read_label_file
from ui.theme import T, mono_font, class_color
from ui.icons import icon, ICON_SIZE_SM
from ui.widgets import (
    Toolbar, StatusBar, Segment, chip, button, ghost_button, danger_button,
    primary_button, combo, line_edit, mono_label, vrule, check,
)
from ui.rebalance_dialog import RebalanceDialog

THUMB_W, THUMB_H = 180, 122
CARD_W = 194


class ImageCard(QFrame):
    """One image, its boxes, and its labelling status."""
    doubleClicked = Signal(str)
    selectionChanged = Signal(str, bool)

    def __init__(self, filename: str, image_path: Path, label_path: Path,
                 classes_lookup: dict, show_boxes: bool = True,
                 status: str = "unlabeled", parent=None):
        super().__init__(parent)
        self.filename = filename
        self.image_path = image_path
        self.label_path = label_path
        self.classes_lookup = classes_lookup
        self.show_boxes = show_boxes
        self.status = status
        self.is_selected = False
        self.box_count = 0

        self.setObjectName("ImageCard")
        self.setFixedSize(CARD_W, THUMB_H + 44)
        self.setCursor(Qt.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.thumb_lbl = QLabel()
        self.thumb_lbl.setFixedSize(CARD_W - 2, THUMB_H)
        self.thumb_lbl.setAlignment(Qt.AlignCenter)
        self.thumb_lbl.setStyleSheet(
            f"background:{T.INK_950};border-top-left-radius:{T.R}px;"
            f"border-top-right-radius:{T.R}px;")
        lay.addWidget(self.thumb_lbl)

        meta = QWidget()
        ml = QHBoxLayout(meta)
        ml.setContentsMargins(9, 7, 9, 7)
        ml.setSpacing(7)
        self.chk = QCheckBox()
        self.chk.setFixedSize(16, 16)
        self.chk.toggled.connect(self._on_chk_toggled)
        ml.addWidget(self.chk)

        self.name_lbl = mono_label(Path(filename).stem, T.FS_MICRO, T.TX_2)
        self.name_lbl.setToolTip(filename)
        self.name_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        ml.addWidget(self.name_lbl, stretch=1)

        self.count_lbl = mono_label("", T.FS_MICRO, T.TX_3)
        ml.addWidget(self.count_lbl)
        lay.addWidget(meta)

        self._render_thumbnail()
        self._update_style()

    def _update_style(self):
        border = T.ACCENT if self.is_selected else T.LINE
        self.setStyleSheet(
            f"QFrame#ImageCard{{background:{T.INK_850};border:1px solid {border};"
            f"border-radius:{T.R}px;}}")

    def _render_thumbnail(self):
        if not self.image_path.exists():
            self.thumb_lbl.setText("missing")
            return
        pix = QPixmap(str(self.image_path))
        if pix.isNull():
            self.thumb_lbl.setText("unreadable")
            self.thumb_lbl.setStyleSheet(
                f"background:{T.INK_950};color:{T.DANGER_TEXT};"
                f"font-size:{T.FS_SMALL}px;")
            return

        w, h = pix.width(), pix.height()
        scaled = pix.scaled(CARD_W - 2, THUMB_H, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        boxes = read_label_file(self.label_path).boxes if self.label_path.exists() else []
        self.box_count = len(boxes)

        if self.show_boxes and boxes:
            painter = QPainter(scaled)
            painter.setRenderHint(QPainter.Antialiasing)
            sx = scaled.width() / float(w)
            sy = scaled.height() / float(h)
            for b in boxes:
                _name, color_hex = self.classes_lookup.get(
                    b.class_id, (f"class{b.class_id}", class_color(b.class_id)))
                col = QColor(color_hex)
                fill = QColor(col)
                fill.setAlpha(38)
                painter.setPen(QPen(col, 1.6))
                painter.setBrush(QBrush(fill))
                if b.is_polygon:
                    pts = [QPointF(px * sx, py * sy)
                           for px, py in b.polygon_pixels(w, h)]
                    painter.drawPolygon(QPolygonF(pts))
                else:
                    x1, y1, x2, y2 = b.to_pixels(w, h)
                    painter.drawRect(QRectF(x1 * sx, y1 * sy,
                                            (x2 - x1) * sx, (y2 - y1) * sy))
            painter.end()

        # status pill, burned into the corner
        pill_text, pill_bg = {
            "labeled": ("reviewed", T.OK),
            "auto-labeled": ("auto", T.ACCENT),
        }.get(self.status, ("no boxes", T.WARN))
        if self.status not in ("labeled", "auto-labeled") and self.box_count:
            pill_text, pill_bg = "auto", T.ACCENT
        painter = QPainter(scaled)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setFont(mono_font(T.FS_MICRO - 1))
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(pill_text) + 10
        th = fm.height() + 3
        painter.setPen(Qt.NoPen)
        bg = QColor(pill_bg)
        bg.setAlpha(232)
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(QRectF(5, 5, tw, th), 3, 3)
        painter.setPen(QPen(QColor(T.INK_950)))
        painter.drawText(QRectF(5, 5, tw, th), Qt.AlignCenter, pill_text)
        painter.end()

        self.thumb_lbl.setPixmap(scaled)
        self.count_lbl.setText(str(self.box_count))
        self.count_lbl.setStyleSheet(
            f"color:{T.WARN if self.box_count == 0 else T.TX_3};background:transparent;")

    def set_show_boxes(self, show: bool):
        self.show_boxes = show
        self._render_thumbnail()

    def set_selected(self, sel: bool):
        self.is_selected = sel
        self.chk.blockSignals(True)
        self.chk.setChecked(sel)
        self.chk.blockSignals(False)
        self._update_style()

    def _on_chk_toggled(self, checked: bool):
        self.is_selected = checked
        self._update_style()
        self.selectionChanged.emit(self.filename, checked)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit(self.filename)
        super().mouseDoubleClickEvent(event)


class DatasetView(QWidget):
    openImageRequested = Signal(str)
    autoLabelSelectedRequested = Signal(list)
    autoLabelAllRequested = Signal()
    loadModelRequested = Signal()
    deleteSelectedRequested = Signal(list)
    exportRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.pm = None
        self.selected_files: Set[str] = set()
        self.cards: List[ImageCard] = []
        self.current_page = 1
        self.items_per_page = 60

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_toolbar())
        root.addWidget(self._build_splitbar())
        root.addWidget(self._build_batchbar())
        root.addWidget(self._build_filterbar())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.grid_widget = QWidget()
        self.grid_widget.setObjectName("Page")
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setContentsMargins(T.S5, T.S4, T.S5, T.S5)
        self.grid_layout.setSpacing(T.S3)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(self.grid_widget)
        root.addWidget(scroll, stretch=1)

        self.status = StatusBar()
        root.addWidget(self.status)

        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._restore_status)
        self.set_model_state("idle", "")

    # ------------------------------------------------------------- toolbar
    def _build_toolbar(self) -> Toolbar:
        tb = Toolbar("Dataset")

        self.model_lbl = mono_label("no model", T.FS_SMALL, T.TX_3)
        self.model_lbl.setToolTip("Weights used for auto-labelling")
        tb.add(self.model_lbl)

        self.btn_model = ghost_button("Model", "Load YOLO weights (.pt)", "brain", "sm")
        self.btn_model.clicked.connect(self.loadModelRequested)
        tb.add(self.btn_model)

        tb.add(vrule())
        conf_lbl = QLabel("conf")
        conf_lbl.setObjectName("Muted")
        tb.add(conf_lbl)
        self.conf_spin = QDoubleSpinBox()
        self.conf_spin.setRange(0.05, 0.95)
        self.conf_spin.setSingleStep(0.05)
        self.conf_spin.setFixedWidth(66)
        self.conf_spin.setFont(mono_font(T.FS_CONTROL))
        from core.config import settings
        self.conf_spin.setValue(float(settings().get("confidence", 0.25)))
        self.conf_spin.valueChanged.connect(
            lambda v: settings().set("confidence", round(v, 2)))
        self.conf_spin.setToolTip("Confidence threshold for auto-labelling")
        tb.add(self.conf_spin)

        self.btn_autolabel = primary_button(
            "Auto-label", "Label every image that has no boxes yet", "play", "sm")
        self.btn_autolabel.clicked.connect(self.autoLabelAllRequested)
        tb.add(self.btn_autolabel)

        self.btn_export = button("Export", "Build a train/val dataset", "box", "sm")
        self.btn_export.clicked.connect(self.exportRequested)
        tb.add(self.btn_export)
        return tb

    def _build_splitbar(self) -> QWidget:
        """Train / Valid / Test / Default, the way Roboflow tabs its images."""
        bar = QWidget()
        bar.setObjectName("Toolbar")
        bar.setFixedHeight(38)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(T.S4, 0, T.S4, 0)
        lay.setSpacing(0)

        self.split_tabs = {}
        for key, label in (("all", "All"), ("train", "Train"), ("valid", "Valid"),
                           ("test", "Test"), ("default", "Unassigned")):
            tab = QPushButton(label)
            tab.setCheckable(True)
            tab.setCursor(Qt.PointingHandCursor)
            tab.setProperty("variant", "tab")
            tab.setChecked(key == "all")
            tab.clicked.connect(lambda _=False, k=key: self._pick_split(k))
            self.split_tabs[key] = tab
            lay.addWidget(tab)
        lay.addStretch()

        self.btn_rebalance = ghost_button(
            "Rebalance…", "Deal every image into train / valid / test",
            "layers", "sm")
        self.btn_rebalance.clicked.connect(self._rebalance)
        lay.addWidget(self.btn_rebalance)
        self._current_split = "all"
        return bar

    def _pick_split(self, key: str):
        self._current_split = key
        for k, tab in self.split_tabs.items():
            tab.setChecked(k == key)
        self.current_page = 1
        self.refresh()

    def _refresh_split_tabs(self):
        if not self.pm:
            return
        counts = self.pm.split_counts()
        labels = {"all": "All", "train": "Train", "valid": "Valid",
                  "test": "Test", "default": "Unassigned"}
        for key, tab in self.split_tabs.items():
            n = counts.get(key, 0)
            tab.setText(f"{labels[key]}  {n:,}")
            # never hide a tab that is currently selected, even when empty
            tab.setEnabled(n > 0 or key in ("all", self._current_split))

    def _rebalance(self):
        if not self.pm:
            return
        dlg = RebalanceDialog(self, total=len(self.pm.get_images()),
                              counts=self.pm.split_counts())
        if not dlg.exec():
            return
        res = self.pm.rebalance_splits(
            train=dlg.train, valid=dlg.valid, test=dlg.test,
            seed=dlg.seed, only_unassigned=dlg.only_unassigned)
        self.refresh()
        self.flash(f"train {res['train']:,} · valid {res['valid']:,} · "
                   f"test {res['test']:,}")

    def assign_split(self, split: str):
        """Put the currently selected images into a split."""
        if not self.pm or not self.selected_files:
            return
        n = self.pm.set_splits(sorted(self.selected_files), split)
        self.refresh()
        self.flash(f"Moved {n:,} image(s) to "
                   + (split or "unassigned"))

    def _build_batchbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("BatchBar")
        bar.setFixedHeight(T.TOOLBAR_H)
        bar.setStyleSheet(
            f"QWidget#BatchBar{{background:{T.ACCENT_WASH};"
            f"border-bottom:1px solid {T.ACCENT_DIM};}}")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(T.S4, 0, T.S4, 0)
        lay.setSpacing(T.S2)

        self.sel_lbl = mono_label("0 selected", T.FS_CONTROL, "#BFD6FF")
        lay.addWidget(self.sel_lbl)
        lay.addWidget(vrule())

        b1 = button("Auto-label these", icon_name="play", size="sm")
        b1.clicked.connect(self._on_autolabel_selected)
        b2 = danger_button("Delete", "Moves to .trash — undo with Ctrl+Shift+Z",
                           "trash", "sm")
        b2.clicked.connect(self._on_delete_selected)
        lay.addWidget(b1)
        lay.addWidget(vrule())
        move_lbl = QLabel("Move to")
        move_lbl.setObjectName("Muted")
        lay.addWidget(move_lbl)
        for key, label in (("train", "Train"), ("valid", "Valid"),
                           ("test", "Test"), ("", "Unassigned")):
            sb = button(label, f"Assign the selected images to {label.lower()}",
                        size="sm")
            sb.clicked.connect(lambda _=False, k=key: self.assign_split(k))
            lay.addWidget(sb)
        lay.addWidget(vrule())
        lay.addWidget(b2)
        lay.addStretch()
        clear = ghost_button("Clear selection", size="sm")
        clear.clicked.connect(self._clear_selection)
        lay.addWidget(clear)

        self.batch_bar = bar
        bar.setVisible(False)
        return bar

    def _build_filterbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("Toolbar")
        bar.setFixedHeight(T.TOOLBAR_H)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(T.S4, 0, T.S4, 0)
        lay.setSpacing(T.S2)

        self.search_edit = line_edit("Search filenames", width=190)
        self.search_edit.textChanged.connect(self._on_filter_changed)
        lay.addWidget(self.search_edit)

        self.status_chips = []
        for label_text, key in (("All", "all"), ("Auto", "auto-labeled"),
                                ("Reviewed", "labeled"), ("Empty", "unlabeled")):
            c = chip(label_text)
            c.setProperty("status_key", key)
            c.clicked.connect(lambda _=False, w=c: self._pick_status(w))
            self.status_chips.append(c)
            lay.addWidget(c)
        self.status_chips[0].setChecked(True)

        lay.addWidget(vrule())
        self.class_combo = combo(["All classes"], width=150)
        self.class_combo.currentIndexChanged.connect(self._on_filter_changed)
        lay.addWidget(self.class_combo)

        self.sort_combo = combo(["Newest", "Oldest", "Name"], width=104)
        self.sort_combo.currentIndexChanged.connect(self._on_filter_changed)
        lay.addWidget(self.sort_combo)

        lay.addStretch()
        self.boxes_seg = Segment(["Boxes on", "Off"], 0)
        self.boxes_seg.changed.connect(lambda i: self._toggle_show_boxes(i == 0))
        lay.addWidget(self.boxes_seg)

        lay.addWidget(vrule())
        self.btn_prev_page = ghost_button("", "Previous page", "left", "sm")
        self.btn_prev_page.clicked.connect(self._prev_page)
        self.btn_next_page = ghost_button("", "Next page", "right", "sm")
        self.btn_next_page.clicked.connect(self._next_page)
        lay.addWidget(self.btn_prev_page)
        lay.addWidget(self.btn_next_page)
        return bar

    # --------------------------------------------------------------- state
    def confidence(self) -> float:
        return self.conf_spin.value()

    def set_model_state(self, state: str, name: str, n_classes: int = 0):
        text, color = {
            "loading": (f"loading {name}…", T.TX_2),
            "ready": (f"{name} · {n_classes} classes", T.OK),
            "error": ("model failed to load", T.DANGER_TEXT),
        }.get(state, ("no model loaded", T.TX_3))
        self.model_lbl.setText(text)
        self.model_lbl.setStyleSheet(f"color:{color};background:transparent;")
        self.btn_model.setEnabled(state != "loading")

    def flash(self, message: str, tone: str = ""):
        """Transient feedback in the status bar, instead of a modal dialog."""
        self.status.set_left(message, tone or T.TX_1)
        self._flash_timer.start(6000)

    def _restore_status(self):
        if not self.pm:
            self.status.set_left("no project")
            return
        s = self.pm.stats()
        self.status.set_left(
            f"{s['labeled']} reviewed · {s['auto-labeled']} auto · "
            f"{s['unlabeled']} empty")

    def set_project(self, pm):
        self.pm = pm
        self._refresh_classes_combo()
        self.refresh()

    def _refresh_classes_combo(self):
        self.class_combo.blockSignals(True)
        self.class_combo.clear()
        self.class_combo.addItem("All classes")
        if self.pm:
            from ui.icons import swatch
            for cid, name, col in self.pm.get_classes():
                self.class_combo.addItem(swatch(col, 9), f"{name}", userData=cid)
        self.class_combo.blockSignals(False)

    def _pick_status(self, widget):
        for c in self.status_chips:
            c.setChecked(c is widget)
        self._on_filter_changed()

    def _current_status(self) -> str:
        for c in self.status_chips:
            if c.isChecked():
                return c.property("status_key")
        return "all"

    # ------------------------------------------------------------ rendering
    def refresh(self):
        if not self.pm:
            self._clear_grid()
            self.status.set_left("no project")
            return

        txt = self.search_edit.text().strip()
        images = list(self.pm.get_images(filter_text=txt,
                                         filter_status=self._current_status(),
                                         filter_split=self._current_split))

        class_id = self.class_combo.currentData()
        if class_id is not None:
            images = [r for r in images
                      if any(b.class_id == class_id for b in
                             read_label_file(self.pm.label_path(r["filename"])).boxes)]

        sort_idx = self.sort_combo.currentIndex()
        if sort_idx == 0:
            images.sort(key=lambda r: r["id"], reverse=True)
        elif sort_idx == 1:
            images.sort(key=lambda r: r["id"])
        else:
            images.sort(key=lambda r: r["filename"].lower())

        total = len(images)
        max_page = max(1, (total + self.items_per_page - 1) // self.items_per_page)
        self.current_page = min(max(1, self.current_page), max_page)
        start = (self.current_page - 1) * self.items_per_page
        end = min(start + self.items_per_page, total)

        self.btn_prev_page.setEnabled(self.current_page > 1)
        self.btn_next_page.setEnabled(end < total)

        lookup = {cid: (name, col) for cid, name, col in self.pm.get_classes()}
        show_boxes = self.boxes_seg.current_index() == 0

        self._clear_grid()
        self.cards.clear()
        cols = max(1, (self.grid_widget.width() - T.S5 * 2) // (CARD_W + T.S3)) or 5
        for i, row in enumerate(images[start:end]):
            fname = row["filename"]
            card = ImageCard(fname, self.pm.image_path(fname),
                             self.pm.label_path(fname), lookup,
                             show_boxes=show_boxes, status=row["status"], parent=self)
            card.doubleClicked.connect(lambda f: self.openImageRequested.emit(f))
            card.selectionChanged.connect(self._on_card_selection_changed)
            if fname in self.selected_files:
                card.set_selected(True)
            self.cards.append(card)
            self.grid_layout.addWidget(card, i // cols, i % cols)

        self._refresh_split_tabs()
        self._update_batch_bar()
        self._restore_status()
        self.status.set_right(
            f"{start + 1 if total else 0}–{end} of {total:,}"
            + (f"  ·  page {self.current_page}/{max_page}" if max_page > 1 else ""))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.cards:
            cols = max(1, (self.grid_widget.width() - T.S5 * 2) // (CARD_W + T.S3))
            for i, card in enumerate(self.cards):
                self.grid_layout.addWidget(card, i // cols, i % cols)

    def _clear_grid(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _toggle_show_boxes(self, show: bool):
        for card in self.cards:
            card.set_show_boxes(show)

    def _on_filter_changed(self):
        self.current_page = 1
        self.refresh()

    def _prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.refresh()

    def _next_page(self):
        self.current_page += 1
        self.refresh()

    # ----------------------------------------------------------- selection
    def _on_card_selection_changed(self, filename: str, is_selected: bool):
        if is_selected:
            self.selected_files.add(filename)
        else:
            self.selected_files.discard(filename)
        self._update_batch_bar()

    def _update_batch_bar(self):
        n = len(self.selected_files)
        self.sel_lbl.setText(f"{n} selected")
        self.batch_bar.setVisible(n > 0)

    def _clear_selection(self):
        self.selected_files.clear()
        for card in self.cards:
            card.set_selected(False)
        self._update_batch_bar()

    def _on_autolabel_selected(self):
        if self.selected_files:
            self.autoLabelSelectedRequested.emit(sorted(self.selected_files))

    def _on_delete_selected(self):
        if not self.selected_files or not self.pm:
            return
        files = sorted(self.selected_files)
        if QMessageBox.question(
                self, "Delete images",
                f"Move {len(files)} image(s) and their labels to .trash/?\n\n"
                "Undo with Ctrl+Shift+Z, or from the Trash item in the sidebar.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        n = self.pm.delete_images(files, reason="deleted from gallery")
        self.selected_files.clear()
        self.refresh()
        self.flash(f"Moved {n} file(s) to the trash.")
        self.deleteSelectedRequested.emit(files)
