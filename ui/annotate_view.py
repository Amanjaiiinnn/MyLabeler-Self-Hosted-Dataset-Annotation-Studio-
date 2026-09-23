"""
ui/annotate_view.py — the labelling canvas.

A filmstrip on the left so you can see what is coming, the canvas in the middle,
and one right-hand panel that stacks classes above the selected box, so your
hand stays on one side of the screen.
"""
from __future__ import annotations
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QBrush, QPolygonF
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSplitter, QScrollArea,
    QSizePolicy,
)

from core.annotation import read_label_file, save_yolo_annotations
from ui.canvas import Canvas
from ui.class_panel import ClassPanel
from ui.label_inspector import LabelInspector
from ui.theme import T, mono_font, class_color
from ui.icons import icon
from ui.widgets import (
    Toolbar, StatusBar, Segment, button, ghost_button, mono_label, vrule, kbd,
)

FILM_W = 96
THUMB_W, THUMB_H = 80, 60


class FilmFrame(QFrame):
    """One thumbnail in the filmstrip."""
    clicked = Signal(str)

    def __init__(self, filename: str, image_path: Path, label_path: Path,
                 lookup: dict, status: str, parent=None):
        super().__init__(parent)
        self.filename = filename
        self.setObjectName("FilmFrame")
        self.setFixedSize(THUMB_W, THUMB_H + 14)
        self.setCursor(Qt.PointingHandCursor)
        self._current = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)

        self.thumb = QLabel()
        self.thumb.setFixedSize(THUMB_W, THUMB_H)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet(f"background:{T.INK_950};border-radius:{T.R_SM}px;")
        lay.addWidget(self.thumb)

        cap = mono_label(Path(filename).stem[-9:], T.FS_MICRO - 1, T.TX_3)
        cap.setAlignment(Qt.AlignCenter)
        lay.addWidget(cap)

        self._render(image_path, label_path, lookup)
        self._apply_style()

    def _render(self, image_path: Path, label_path: Path, lookup: dict):
        pix = QPixmap(str(image_path))
        if pix.isNull():
            return
        w, h = pix.width(), pix.height()
        scaled = pix.scaled(THUMB_W, THUMB_H, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        boxes = read_label_file(label_path).boxes if label_path.exists() else []
        if boxes:
            p = QPainter(scaled)
            p.setRenderHint(QPainter.Antialiasing)
            sx, sy = scaled.width() / w, scaled.height() / h
            for b in boxes:
                _n, col = lookup.get(b.class_id,
                                     (f"class{b.class_id}", class_color(b.class_id)))
                p.setPen(QPen(QColor(col), 1.3))
                p.setBrush(Qt.NoBrush)
                if b.is_polygon:
                    p.drawPolygon(QPolygonF([QPointF(px * sx, py * sy)
                                             for px, py in b.polygon_pixels(w, h)]))
                else:
                    x1, y1, x2, y2 = b.to_pixels(w, h)
                    p.drawRect(QRectF(x1 * sx, y1 * sy, (x2 - x1) * sx, (y2 - y1) * sy))
            p.end()
        self.thumb.setPixmap(scaled)

    def set_current(self, on: bool):
        self._current = on
        self._apply_style()

    def _apply_style(self):
        border = T.ACCENT if self._current else "transparent"
        self.setStyleSheet(
            f"QFrame#FilmFrame{{border:1.5px solid {border};border-radius:{T.R_SM + 1}px;}}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.filename)
        super().mousePressEvent(event)


class AnnotateView(QWidget):
    backToDatasetRequested = Signal()
    annotationsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.pm = None
        self.current_filename: Optional[str] = None
        self._frames: List[FilmFrame] = []

        self.canvas = Canvas()
        self.canvas.boxesChanged.connect(self._on_boxes_changed)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_toolbar())

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)

        # filmstrip
        film_wrap = QWidget()
        film_wrap.setObjectName("Rail")
        film_wrap.setFixedWidth(FILM_W)
        fw = QVBoxLayout(film_wrap)
        fw.setContentsMargins(0, T.S2, 0, 0)
        fw.setSpacing(T.S2)
        film_cap = QLabel("IMAGES")
        film_cap.setObjectName("SectionLabel")
        film_cap.setAlignment(Qt.AlignCenter)
        fw.addWidget(film_cap)
        self.film_scroll = QScrollArea()
        self.film_scroll.setWidgetResizable(True)
        self.film_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.film_inner = QWidget()
        self.film_lay = QVBoxLayout(self.film_inner)
        self.film_lay.setContentsMargins(T.S2, 0, T.S2, T.S2)
        self.film_lay.setSpacing(5)
        self.film_lay.setAlignment(Qt.AlignTop)
        self.film_scroll.setWidget(self.film_inner)
        fw.addWidget(self.film_scroll, stretch=1)
        split.addWidget(film_wrap)

        # canvas
        canvas_wrap = QWidget()
        canvas_wrap.setObjectName("Canvas")
        cw = QHBoxLayout(canvas_wrap)
        cw.setContentsMargins(0, 0, T.S2, 0)
        cw.setSpacing(T.S2)
        cw.addWidget(self.canvas, stretch=1)
        rail_col = QVBoxLayout()
        rail_col.setContentsMargins(0, T.S2, 0, T.S2)
        rail_col.addWidget(self._build_tool_rail())
        rail_col.addStretch()
        cw.addLayout(rail_col)
        split.addWidget(canvas_wrap)

        # right panel
        panel = QWidget()
        panel.setObjectName("Panel")
        panel.setFixedWidth(272)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(0)

        self.class_panel = ClassPanel()
        self.class_panel.classSelected.connect(self._on_class_selected)
        self.class_panel.classesChanged.connect(self._refresh_class_lookup)
        pl.addWidget(self.class_panel, stretch=1)

        self.inspector = LabelInspector()
        self.canvas.boxSelected.connect(self.inspector.update_from_box)
        self.inspector.deleteRequested.connect(self.canvas.delete_selected)
        self.inspector.duplicateRequested.connect(self.canvas.duplicate_selected)
        self.inspector.lockToggled.connect(self.canvas.set_lock_selected)
        self.inspector.classChangeRequested.connect(self.canvas.set_selected_class)
        self.inspector.geometryEdited.connect(self.canvas.set_selected_geometry)
        pl.addWidget(self.inspector, stretch=1)
        split.addWidget(panel)

        split.setStretchFactor(1, 1)
        root.addWidget(split, stretch=1)

        self.status = StatusBar()
        root.addWidget(self.status)

        self.canvas.undoAvailable.connect(self.btn_undo.setEnabled)
        self.canvas.redoAvailable.connect(self.btn_redo.setEnabled)
        self.btn_undo.setEnabled(False)
        self.btn_redo.setEnabled(False)

    # ------------------------------------------------------------- toolbar
    def _build_toolbar(self) -> Toolbar:
        """Mirrors Roboflow's annotator bar: crumb, counter, nav, status pill."""
        tb = Toolbar()
        back = ghost_button("Dataset", "Back to the gallery", "left", "sm")
        back.clicked.connect(self.backToDatasetRequested)
        tb.add(back)
        tb.add(vrule())

        self.title_lbl = mono_label("no image", T.FS_CONTROL, T.TX_1)
        tb.add_left(self.title_lbl)

        self.mode_seg = Segment(["Select", "Draw"], 0)
        self.mode_seg.changed.connect(lambda i: self.canvas.set_draw_mode(i == 1))
        self.mode_seg.buttons[0].setToolTip("Select and edit boxes  (V)")
        self.mode_seg.buttons[1].setToolTip("Draw a new box  (D)")
        tb.add(self.mode_seg)

        self.btn_undo = ghost_button("", "Undo  (Ctrl+Z)", "undo", "sm")
        self.btn_undo.clicked.connect(self.canvas.undo)
        self.btn_redo = ghost_button("", "Redo  (Ctrl+Y)", "redo", "sm")
        self.btn_redo.clicked.connect(self.canvas.redo)
        tb.add(self.btn_undo, self.btn_redo, vrule())

        prev_b = ghost_button("", "Previous image  (Left)", "left", "sm")
        prev_b.clicked.connect(self._prev_image)
        self.pos_lbl = mono_label("0 / 0", T.FS_CONTROL, T.TX_2)
        self.pos_lbl.setAlignment(Qt.AlignCenter)
        self.pos_lbl.setFixedWidth(84)
        next_b = ghost_button("", "Next image  (Right)", "right", "sm")
        next_b.clicked.connect(self._next_image)
        tb.add(prev_b, self.pos_lbl, next_b, vrule())

        # Roboflow shows a VALID / review-status pill here; ours reports the
        # review state the app actually tracks.
        self.status_btn = button("", "Mark this image reviewed", "check", "sm")
        self.status_btn.setFixedWidth(104)
        self.status_btn.clicked.connect(self._toggle_reviewed)
        tb.add(self.status_btn)
        return tb

    def _set_status_pill(self, reviewed: bool):
        self.status_btn.setText("  Reviewed" if reviewed else "  Unreviewed")
        self.status_btn.setProperty("variant", "primary" if reviewed else "")
        self.status_btn.setIcon(icon("check", T.ON_ACCENT if reviewed else T.TX_2))
        self.status_btn.style().unpolish(self.status_btn)
        self.status_btn.style().polish(self.status_btn)

    def _toggle_reviewed(self):
        if not (self.pm and self.current_filename):
            return
        row = self.pm.get_image(self.current_filename)
        now_reviewed = bool(row and row["status"] == "labeled")
        boxes = self.canvas.get_boxes()
        if now_reviewed:
            self.pm.set_status(self.current_filename,
                               "auto-labeled" if boxes else "unlabeled")
        else:
            self.pm.set_status(self.current_filename,
                               "labeled" if boxes else "unlabeled")
        self._set_status_pill(not now_reviewed)
        self.annotationsChanged.emit()

    # ------------------------------------------------------- side tool rail
    def _build_tool_rail(self) -> QWidget:
        """Floating vertical tool strip, like the one on the right of theirs."""
        rail = QFrame()
        rail.setObjectName("ToolRail")
        rail.setFixedWidth(40)
        rail.setStyleSheet(
            f"QFrame#ToolRail{{background:{T.INK_850};border:1px solid {T.LINE};"
            f"border-radius:{T.R}px;}}")
        lay = QVBoxLayout(rail)
        lay.setContentsMargins(4, 6, 4, 6)
        lay.setSpacing(3)

        def tool(icon_name, tip, fn):
            b = ghost_button("", tip, icon_name, "sm")
            b.setFixedSize(32, 30)
            b.clicked.connect(fn)
            lay.addWidget(b)
            return b

        tool("fit", "Zoom to fit  (F)", self.canvas.fit_to_view)
        tool("zoom", "Zoom 1:1  (Ctrl+1)", self.canvas.zoom_to_100)
        lay.addSpacing(T.S2)
        tool("copy", "Duplicate selected  (Ctrl+D)", self.canvas.duplicate_selected)
        tool("lock", "Lock / unlock selected  (L)", self.canvas.toggle_lock_selected)
        tool("trash", "Delete selected  (Del)", self.canvas.delete_selected)
        lay.addStretch()
        return rail

    # ---------------------------------------------------------------- data    # ---------------------------------------------------------------- data
    def set_project(self, pm):
        self.pm = pm
        self.class_panel.set_project(pm)
        self._refresh_class_lookup()
        self._rebuild_film()

    def _refresh_class_lookup(self):
        if self.pm:
            classes = self.pm.get_classes()
            self.canvas.set_classes(classes)
            self.inspector.set_classes(classes)

    def _filenames(self) -> List[str]:
        return [r["filename"] for r in self.pm.get_images()] if self.pm else []

    def _rebuild_film(self):
        while self.film_lay.count():
            w = self.film_lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._frames.clear()
        if not self.pm:
            return
        lookup = {cid: (n, c) for cid, n, c in self.pm.get_classes()}
        for row in self.pm.get_images()[:400]:
            fn = row["filename"]
            f = FilmFrame(fn, self.pm.image_path(fn), self.pm.label_path(fn),
                          lookup, row["status"])
            f.clicked.connect(self.load_image)
            f.set_current(fn == self.current_filename)
            self._frames.append(f)
            self.film_lay.addWidget(f)

    def set_draw_mode(self, on: bool):
        self.mode_seg.set_current_index(1 if on else 0)
        self.canvas.set_draw_mode(on)

    def load_image(self, filename: str):
        if not self.pm:
            return
        self.save_current()
        img_p = self.pm.image_path(filename)
        if not img_p.exists():
            self.status.set_left(f"{filename} is missing", T.DANGER_TEXT)
            return
        self.current_filename = filename
        ok = self.canvas.load_image(str(img_p))
        if not ok:
            self.status.set_left(f"{filename} could not be opened", T.DANGER_TEXT)
            return
        lf = read_label_file(self.pm.label_path(filename))
        self.canvas.load_boxes(lf.boxes)
        self._update_header(lf)
        for f in self._frames:
            f.set_current(f.filename == filename)

    def _update_header(self, lf=None):
        if not self.current_filename:
            return
        self.title_lbl.setText(self.current_filename)
        names = self._filenames()
        if self.current_filename in names:
            self.pos_lbl.setText(
                f"{names.index(self.current_filename) + 1} / {len(names)}")
        row = self.pm.get_image(self.current_filename) if self.pm else None
        self._set_status_pill(bool(row and row["status"] == "labeled"))
        row = self.pm.get_image(self.current_filename) if self.pm else None
        self._set_status_pill(bool(row and row["status"] == "labeled"))
        boxes = self.canvas.get_boxes()
        polys = sum(1 for b in boxes if b.is_polygon)
        parts = [f"{len(boxes)} box{'es' if len(boxes) != 1 else ''}"]
        if polys:
            parts.append(f"{polys} OBB")
        if self.canvas.img_w:
            parts.append(f"{self.canvas.img_w}×{self.canvas.img_h}")
        self.status.set_left("saved", T.OK)
        self.status.set_right("  ·  ".join(parts))

    def save_current(self):
        if not self.pm or not self.current_filename:
            return
        if not self.canvas.img_w:
            return
        boxes = self.canvas.get_boxes()
        save_yolo_annotations(self.pm.label_path(self.current_filename), boxes)
        self.pm.set_status(self.current_filename, "labeled" if boxes else "unlabeled")
        self.annotationsChanged.emit()

    def _on_boxes_changed(self):
        self.save_current()
        self._update_header()

    def _on_class_selected(self, class_id: int):
        self.canvas.set_current_class(class_id)
        if self.canvas.selected_box():
            self.canvas.set_selected_class(class_id)

    def _prev_image(self):
        names = self._filenames()
        if self.current_filename in names:
            i = names.index(self.current_filename)
            if i > 0:
                self.load_image(names[i - 1])

    def _next_image(self):
        names = self._filenames()
        if self.current_filename in names:
            i = names.index(self.current_filename)
            if i + 1 < len(names):
                self.load_image(names[i + 1])
