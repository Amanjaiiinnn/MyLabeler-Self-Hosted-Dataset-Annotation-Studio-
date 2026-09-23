"""
ui/review_view.py — fast keyboard review of a dataset.

The PySide port of MAIN_label_id_fix_ui.py and review_and_clean.py: pick a
working set (one class / empty / multiclass / malformed / unlabeled), then walk
it with the arrow keys, changing class ids or trashing bad samples as you go.

Unlike the Tk original, Delete is undoable — pairs go to .trash/.
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import (
    QPixmap, QPainter, QColor, QPen, QBrush, QFont, QPolygonF, QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QMessageBox,
    QSizePolicy, QFrame, QGridLayout,
)

from core import labelops as ops
from core.annotation import read_label_file, save_yolo_annotations
from core.dataset_source import Pair
from core.project import DEFAULT_COLORS
from core.trash import Trash
from ui.theme import T
from ui.widgets import (
    Card, DatasetPicker, button, combo, danger_button, ghost_button,
    line_edit, page_title, primary_button, vrule, kbd,
)

FILTERS = [
    ("All images", ops.REVIEW_ALL),
    ("Empty labels (0 boxes)", ops.REVIEW_EMPTY),
    ("Multiclass images", ops.REVIEW_MULTICLASS),
    ("Malformed label lines", ops.REVIEW_MALFORMED),
    ("No label file at all", ops.REVIEW_UNLABELED),
]


class ImageStage(QLabel):
    """Draws the current image with its boxes and OBB polygons burned in."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(560, 420)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        pass  # styled by ui/theme.py
        self._pair: Optional[Pair] = None
        self._colors: Dict[int, str] = {}
        self._names: Dict[int, str] = {}
        self.setText("Nothing selected")

    def set_palette(self, colors: Dict[int, str], names: Dict[int, str]):
        self._colors, self._names = colors, names

    def show_pair(self, pair: Optional[Pair]):
        self._pair = pair
        self.render_now()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.render_now()

    def render_now(self):
        pair = self._pair
        if pair is None or not pair.has_image:
            self.setPixmap(QPixmap())
            self.setText("DONE — nothing left in this filter"
                         if pair is None else "Image missing")
            return

        pix = QPixmap(str(pair.image))
        if pix.isNull():
            self.setPixmap(QPixmap())
            self.setText(f"Could not open\n{pair.image.name}")
            return

        img_w, img_h = pix.width(), pix.height()
        avail = self.size()
        scaled = pix.scaled(max(64, avail.width() - 12), max(64, avail.height() - 12),
                            Qt.KeepAspectRatio, Qt.SmoothTransformation)
        sx = scaled.width() / img_w
        sy = scaled.height() / img_h

        boxes = read_label_file(pair.label).boxes if pair.has_label else []
        if boxes:
            painter = QPainter(scaled)
            painter.setRenderHint(QPainter.Antialiasing)
            from ui.theme import mono_font as _mf; painter.setFont(_mf(9))
            for b in boxes:
                color = QColor(self._colors.get(
                    b.class_id, DEFAULT_COLORS[b.class_id % len(DEFAULT_COLORS)]))
                fill = QColor(color)
                fill.setAlpha(45)
                painter.setPen(QPen(color, 2))
                painter.setBrush(QBrush(fill))
                if b.is_polygon:
                    pts = [QPointF(px * sx, py * sy)
                           for px, py in b.polygon_pixels(img_w, img_h)]
                    painter.drawPolygon(QPolygonF(pts))
                    anchor = min(pts, key=lambda p: p.y())
                    lx, ly = anchor.x(), anchor.y()
                else:
                    x1, y1, x2, y2 = b.to_pixels(img_w, img_h)
                    painter.drawRect(QRectF(x1 * sx, y1 * sy,
                                            (x2 - x1) * sx, (y2 - y1) * sy))
                    lx, ly = x1 * sx, y1 * sy

                name = self._names.get(b.class_id, f"class{b.class_id}")
                tag = f"{name}" + (" ◇" if b.is_polygon else "")
                metrics = painter.fontMetrics()
                tw = metrics.horizontalAdvance(tag) + 8
                th = metrics.height() + 2
                bg = QColor(color)
                bg.setAlpha(230)
                painter.setBrush(QBrush(bg))
                painter.setPen(Qt.NoPen)
                painter.drawRect(QRectF(lx, max(0, ly - th), tw, th))
                painter.setPen(QPen(Qt.white))
                painter.drawText(QRectF(lx + 4, max(0, ly - th), tw, th),
                                 Qt.AlignVCenter | Qt.AlignLeft, tag)
            painter.end()

        self.setText("")
        self.setPixmap(scaled)


class ReviewView(QWidget):
    """Working-set review with keyboard-speed edits."""

    datasetChanged = Signal()
    openInAnnotatorRequested = Signal(str)   # filename, when reviewing the project

    def __init__(self, parent=None):
        super().__init__(parent)
        pass  # styled by ui/theme.py
        self.pm = None
        self.pairs: List[Pair] = []
        self.index = 0
        self._names: Dict[int, str] = {}
        self._colors: Dict[int, str] = {}
        self._source = None
        self._accepted: set = set()
        self.status_note = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(12)

        # ── header ────────────────────────────────────────────
        head = QHBoxLayout()
        head.addWidget(page_title(
            "Review",
            "Walk a filtered slice of the dataset. ← → to move, D to trash, "
            "0-9 to switch the class of every box in the image."), stretch=1)
        root.addLayout(head)

        self.picker = DatasetPicker()
        self.picker.sourceChanged.connect(self.reload)
        root.addWidget(self.picker)

        # ── filter bar ────────────────────────────────────────
        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(QLabel("Show:"))
        self.filter_combo = combo()
        self.filter_combo.setMinimumWidth(240)
        self.filter_combo.currentIndexChanged.connect(lambda _: self.reload())
        bar.addWidget(self.filter_combo)

        bar.addSpacing(14)
        bar.addWidget(QLabel("Go to #"))
        self.jump_edit = line_edit("1")
        self.jump_edit.setFixedWidth(70)
        self.jump_edit.returnPressed.connect(self._jump)
        bar.addWidget(self.jump_edit)
        go = ghost_button("Go")
        go.clicked.connect(self._jump)
        bar.addWidget(go)

        bar.addStretch()

        self.btn_accept_all = button(
            "Accept all", "Mark every image in this filter as reviewed",
            "check", "sm")
        self.btn_accept_all.clicked.connect(self.accept_all)
        self.btn_reject_all = danger_button(
            "Reject all", "Send every image in this filter to .trash",
            "trash", "sm")
        self.btn_reject_all.clicked.connect(self.reject_all)
        bar.addWidget(self.btn_accept_all)
        bar.addWidget(self.btn_reject_all)
        bar.addWidget(vrule())

        self.counter = QLabel("0 / 0")
        self.counter.setObjectName("Title")
        bar.addWidget(self.counter)
        root.addLayout(bar)

        # ── stage + side panel ────────────────────────────────
        body = QHBoxLayout()
        body.setSpacing(14)

        left = QVBoxLayout()
        left.setSpacing(8)
        self.stage = ImageStage()
        left.addWidget(self.stage, stretch=1)

        self.caption = QLabel("")
        self.caption.setObjectName("Caption")
        self.caption.setWordWrap(True)
        left.addWidget(self.caption)

        nav = QHBoxLayout()
        nav.setSpacing(T.S2)
        self.btn_prev = ghost_button("Previous", "Go back one image  (Left)", "left")
        self.btn_prev.clicked.connect(self.prev_image)
        self.btn_skip = ghost_button("Skip", "Move on without a verdict  (K)", "right")
        self.btn_skip.clicked.connect(self.next_image)
        self.btn_accept = primary_button(
            "Accept", "Mark reviewed and advance  (A)", "check")
        self.btn_accept.clicked.connect(self.accept_current)
        self.btn_reject = danger_button(
            "Reject", "Send image + label to .trash and advance  (R)", "trash")
        self.btn_reject.clicked.connect(self.reject_current)
        self.btn_undo = ghost_button("Undo", "Restore the last deleted pair  (Ctrl+Z)",
                                     "undo")
        self.btn_undo.clicked.connect(self._undo)
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.btn_skip)
        nav.addStretch()
        nav.addWidget(self.btn_undo)
        nav.addWidget(self.btn_reject)
        nav.addWidget(self.btn_accept)
        left.addLayout(nav)
        body.addLayout(left, stretch=3)

        # side panel
        side = QVBoxLayout()
        side.setSpacing(12)

        self.info_card = Card("This image")
        self.info_lbl = QLabel("—")
        pass  # styled by ui/theme.py
        self.info_lbl.setWordWrap(True)
        self.info_card.body.addWidget(self.info_lbl)
        self.btn_open_annotator = ghost_button("Open in annotator")
        self.btn_open_annotator.clicked.connect(self._open_in_annotator)
        self.info_card.body.addWidget(self.btn_open_annotator)
        side.addWidget(self.info_card)

        self.class_card = Card("Change class of every box here",
                               "Press the number key shown, or click a button.")
        self.class_grid = QGridLayout()
        self.class_grid.setSpacing(6)
        self.class_card.body.addLayout(self.class_grid)
        side.addWidget(self.class_card)

        self.labels_card = Card("Label file")
        self.labels_lbl = QLabel("—")
        self.labels_lbl.setFont(QFont("Consolas", 9))
        pass  # styled by ui/theme.py
        self.labels_lbl.setWordWrap(True)
        self.labels_lbl.setAlignment(Qt.AlignTop)
        self.labels_card.body.addWidget(self.labels_lbl)
        side.addWidget(self.labels_card)

        side.addStretch()
        side_holder = QWidget()
        side_holder.setLayout(side)
        side_holder.setFixedWidth(310)
        body.addWidget(side_holder)

        root.addLayout(body, stretch=1)

        self._build_shortcuts()
        self._refresh_filters()

    # ------------------------------------------------------------ shortcuts
    def _build_shortcuts(self):
        def sc(key, fn):
            s = QShortcut(QKeySequence(key), self)
            s.setContext(Qt.WidgetWithChildrenShortcut)
            s.activated.connect(fn)
            return s

        sc("Left", self.prev_image)
        sc("Right", self.next_image)
        sc("K", self.next_image)
        sc("A", self.accept_current)
        sc("R", self.reject_current)
        sc("D", self.delete_current)
        sc("Delete", self.delete_current)
        sc("Ctrl+Z", self._undo)
        for n in range(10):
            sc(str(n), lambda i=n: self._set_all_boxes_to_slot(i))

    # ---------------------------------------------------------------- setup
    def set_project(self, pm):
        self.pm = pm
        self.picker.set_project(pm)
        self.reload()

    def refresh(self):
        self.picker.refresh()
        self.reload()

    def _refresh_filters(self, class_ids: Optional[List[int]] = None):
        current = self.filter_combo.currentData()
        self.filter_combo.blockSignals(True)
        self.filter_combo.clear()
        for label, key in FILTERS:
            self.filter_combo.addItem(label, userData=key)
        for cid in (class_ids or []):
            name = self._names.get(cid, f"class{cid}")
            self.filter_combo.addItem(f"Only class [{cid}] {name}", userData=cid)
        idx = self.filter_combo.findData(current)
        self.filter_combo.setCurrentIndex(max(0, idx))
        self.filter_combo.blockSignals(False)

    def reload(self):
        src = self.picker.current_source()
        self._source = src
        if not src or not src.is_valid:
            self.pairs = []
            self._render()
            return

        self._names = dict(src.class_names())
        if self.pm and src.root == self.pm.root:
            self._names = {cid: n for cid, n, _ in self.pm.get_classes()}
            self._colors = {cid: c for cid, _, c in self.pm.get_classes()}
        else:
            self._colors = {cid: DEFAULT_COLORS[cid % len(DEFAULT_COLORS)]
                            for cid in self._names}
        self.stage.set_palette(self._colors, self._names)

        class_ids = sorted(set(self._names) | self._scan_ids(src))
        self._refresh_filters(class_ids)

        selector = self.filter_combo.currentData()
        self.pairs = ops.collect_for_review(src, selector, self.picker.current_splits())
        self.index = 0
        self._build_class_buttons(class_ids)
        self._render()

    def _scan_ids(self, src) -> set:
        ids = set()
        for path in src.label_files(self.picker.current_splits())[:3000]:
            try:
                for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                    tok = line.split()
                    if tok:
                        try:
                            ids.add(int(float(tok[0])))
                        except ValueError:
                            pass
            except OSError:
                continue
        return ids

    def _build_class_buttons(self, class_ids: List[int]):
        while self.class_grid.count():
            w = self.class_grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._slot_ids = list(class_ids)[:10]
        for i, cid in enumerate(self._slot_ids):
            name = self._names.get(cid, f"class{cid}")
            color = self._colors.get(cid, DEFAULT_COLORS[cid % len(DEFAULT_COLORS)])
            b = ghost_button(f"[{i}]  {name}")
            pass  # styled by ui/theme.py
            b.clicked.connect(lambda chk=False, c=cid: self._set_all_boxes_to(c))
            self.class_grid.addWidget(b, i // 1, 0)

    # ------------------------------------------------------------- rendering
    @property
    def current(self) -> Optional[Pair]:
        if 0 <= self.index < len(self.pairs):
            return self.pairs[self.index]
        return None

    def _render(self):
        pair = self.current
        total = len(self.pairs)
        self.counter.setText(f"{min(self.index + 1, total)} / {total}")
        self.stage.show_pair(pair)

        has = pair is not None
        for b in (self.btn_prev, self.btn_skip, self.btn_accept, self.btn_reject):
            b.setEnabled(has)
        for b in (self.btn_accept_all, self.btn_reject_all):
            b.setEnabled(bool(self.pairs))
        self.btn_open_annotator.setEnabled(
            has and self.pm is not None and self._source is not None
            and self._source.root == self.pm.root)
        trash = Trash(self._source.root) if self._source else None
        self.btn_undo.setEnabled(bool(trash and trash.last_batch()))

        if not has:
            self.caption.setText("")
            self.info_lbl.setText("Nothing matches this filter.")
            self.labels_lbl.setText("—")
            return

        self.caption.setText(str(pair.image) if pair.image else str(pair.label))
        lf = read_label_file(pair.label) if pair.has_label else None
        boxes = lf.boxes if lf else []
        ids = sorted({b.class_id for b in boxes})
        polys = sum(1 for b in boxes if b.is_polygon)

        info = [f"<b>{pair.image.name if pair.image else pair.label.name}</b>"]
        if pair.split:
            info.append(f"split: {pair.split}")
        info.append(f"boxes: {len(boxes)}" + (f" ({polys} OBB)" if polys else ""))
        info.append("classes: " + (", ".join(
            f"[{c}] {self._names.get(c, 'class' + str(c))}" for c in ids) or "none"))
        if lf and lf.malformed:
            info.append(f"<span style='color:#f87171'>malformed lines: "
                        f"{len(lf.malformed)}</span>")
        if not pair.has_label:
            info.append("<span style='color:#f87171'>no label file</span>")
        self.info_lbl.setText("<br>".join(info))

        if lf:
            shown = [b.to_yolo_line() for b in boxes[:12]]
            if lf.malformed:
                shown += [f"✗ {m[:50]}" for m in lf.malformed[:4]]
            extra = len(boxes) - 12
            text = "\n".join(shown) or "(empty file)"
            if extra > 0:
                text += f"\n… {extra} more"
            self.labels_lbl.setText(text)
        else:
            self.labels_lbl.setText("(no label file)")

    # --------------------------------------------------------------- actions
    def next_image(self):
        if self.index < len(self.pairs) - 1:
            self.index += 1
            self._render()

    def prev_image(self):
        if self.index > 0:
            self.index -= 1
            self._render()

    def _jump(self):
        try:
            n = int(self.jump_edit.text().strip())
        except ValueError:
            return
        if 1 <= n <= len(self.pairs):
            self.index = n - 1
            self._render()

    def _set_all_boxes_to_slot(self, slot: int):
        ids = getattr(self, "_slot_ids", [])
        if 0 <= slot < len(ids):
            self._set_all_boxes_to(ids[slot])

    def _set_all_boxes_to(self, class_id: int):
        """The change_id() action from the Tk tool, applied to the whole image."""
        pair = self.current
        if not pair or not pair.has_label:
            return
        lf = read_label_file(pair.label)
        if not lf.boxes:
            return
        for b in lf.boxes:
            b.class_id = class_id
        save_yolo_annotations(pair.label, lf.boxes)
        if self.pm and self._source and self._source.root == self.pm.root:
            self.pm.ensure_class(class_id)
        self._render()
        self.datasetChanged.emit()

    # ------------------------------------------------------- accept / reject
    def _mark_reviewed(self, pair) -> bool:
        """Promote auto-labeled -> labeled. Only meaningful for the open project."""
        if not (self.pm and self._source and self._source.root == self.pm.root):
            return False
        if not pair.image:
            return False
        boxes = read_label_file(pair.label).boxes if pair.has_label else []
        self.pm.set_status(pair.image.name, "labeled" if boxes else "unlabeled")
        return True

    def accept_current(self):
        """Confirm this image's labels are correct, then advance."""
        pair = self.current
        if not pair:
            return
        tracked = self._mark_reviewed(pair)
        self._accepted.add(pair.stem)
        self.datasetChanged.emit()
        if not tracked:
            self.status_note = "accepted (external dataset — status not stored)"
        self._advance_after_verdict()

    def reject_current(self):
        """Send this image and its label to the trash, then advance."""
        pair = self.current
        if not pair or not self._source:
            return
        ops.trash_pairs([pair], Trash(self._source.root), reason="review: rejected")
        if self.pm and self._source.root == self.pm.root and pair.image:
            try:
                self.pm._conn.execute("DELETE FROM images WHERE filename=?",
                                      (pair.image.name,))
                self.pm._conn.commit()
            except Exception:
                pass
        self.pairs.pop(self.index)
        if self.index >= len(self.pairs):
            self.index = max(0, len(self.pairs) - 1)
        self._render()
        self.datasetChanged.emit()

    # kept so existing callers and the D key still work
    def delete_current(self):
        self.reject_current()

    def _advance_after_verdict(self):
        if self.index < len(self.pairs) - 1:
            self.index += 1
        self._render()

    def accept_all(self):
        """Mark every image in the current working set as reviewed."""
        if not self.pairs:
            return
        n = len(self.pairs)
        if QMessageBox.question(
                self, "Accept all",
                f"Mark all {n:,} image(s) in this filter as reviewed?\n\n"
                "Boxes are not changed — this only records that you have "
                "checked them.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        marked = 0
        for pair in self.pairs:
            if self._mark_reviewed(pair):
                marked += 1
            self._accepted.add(pair.stem)
        self.datasetChanged.emit()
        self.reload()
        QMessageBox.information(
            self, "Accepted",
            f"Marked {marked:,} image(s) as reviewed."
            + ("" if marked == n else
               f"\n\n{n - marked:,} were in an external folder, where review "
               f"status is not stored."))

    def reject_all(self):
        """Send every image in the current working set to the trash."""
        if not self.pairs or not self._source:
            return
        n = len(self.pairs)
        box = QMessageBox(self)
        box.setWindowTitle("Reject all")
        box.setIcon(QMessageBox.Warning)
        box.setText(f"Send all {n:,} image(s) in this filter to .trash?")
        box.setInformativeText(
            "Their label files go too. This is recoverable — Undo, or the Trash "
            "item in the sidebar.")
        reject_btn = box.addButton(f"Reject {n:,}", QMessageBox.DestructiveRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.setDefaultButton(box.buttons()[-1])
        box.exec()
        if box.clickedButton() is not reject_btn:
            return

        trash = Trash(self._source.root)
        moved = ops.trash_pairs(self.pairs, trash, reason="review: rejected in bulk")
        if self.pm and self._source.root == self.pm.root:
            for pair in self.pairs:
                if pair.image:
                    try:
                        self.pm._conn.execute(
                            "DELETE FROM images WHERE filename=?", (pair.image.name,))
                    except Exception:
                        pass
            self.pm._conn.commit()
        self.datasetChanged.emit()
        self.reload()
        QMessageBox.information(self, "Rejected",
                                f"Moved {moved:,} file(s) to the trash.")

    def _undo(self):
        if not self._source:
            return
        trash = Trash(self._source.root)
        n = trash.undo_last()
        if not n:
            return
        if self.pm and self._source.root == self.pm.root:
            self.pm._sync_existing_files()
        QMessageBox.information(self, "Undo", f"Restored {n} file(s).")
        self.reload()
        self.datasetChanged.emit()

    def _open_in_annotator(self):
        pair = self.current
        if pair and pair.image:
            self.openInAnnotatorRequested.emit(pair.image.name)
