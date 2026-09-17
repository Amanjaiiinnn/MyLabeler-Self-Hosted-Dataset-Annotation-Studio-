"""
ui/classes_view.py — class names, colours and distribution.

The table is the page. Class ids that appear in label files but have no name
are flagged here, because that is exactly what makes an export produce
`class6` instead of something meaningful.
"""
from __future__ import annotations
from typing import Dict, List

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QInputDialog, QColorDialog, QMessageBox,
    QSizePolicy,
)

from core.annotation import read_label_file
from ui.theme import T, mono_font, class_color
from ui.icons import icon, swatch, dot
from ui.widgets import (
    Toolbar, StatusBar, Card, Banner, StatStrip, Meter, button, ghost_button,
    danger_button, primary_button, mono_label, vrule, combo, line_edit,
)


class ClassesView(QWidget):
    classesUpdated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.pm = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        tb = Toolbar("Classes")
        tb.set_subtitle("")
        self.btn_reindex = button(
            "Close gaps", "Renumber classes to 0..n-1 across every label file",
            "layers", "sm")
        self.btn_reindex.clicked.connect(self._reindex)
        sort_lbl = QLabel("Sort by")
        sort_lbl.setObjectName("Muted")
        self.sort_combo = combo(["Class ascending", "Name", "Most boxes",
                                 "Fewest boxes"], width=150)
        self.sort_combo.currentIndexChanged.connect(lambda _: self.refresh())
        tb.add(self.btn_reindex, vrule(), sort_lbl, self.sort_combo)
        root.addWidget(tb)

        # ── search / add row ──────────────────────────────────
        bar = QWidget()
        bar.setObjectName("Toolbar")
        bar.setFixedHeight(T.TOOLBAR_H)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(T.S6, 0, T.S6, 0)
        bl.setSpacing(T.S2)
        self.search = line_edit("Search classes", width=230)
        self.search.textChanged.connect(self.refresh)
        bl.addWidget(self.search)
        self.btn_add = primary_button("Add", "Create a new category", "plus", "sm")
        self.btn_add.clicked.connect(self._add_class)
        bl.addWidget(self.btn_add)
        bl.addStretch()
        self.count_lbl = mono_label("", T.FS_SMALL, T.TX_3)
        bl.addWidget(self.count_lbl)
        root.addWidget(bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("Page")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(T.S6, T.S5, T.S6, T.S5)
        lay.setSpacing(T.S4)

        self.stats = StatStrip()
        self.tile_classes = self.stats.add_tile("Classes", "0", "defined here")
        self.tile_boxes = self.stats.add_tile("Annotations", "0", "across the dataset")
        self.tile_images = self.stats.add_tile("Annotated images", "0", "have at least one box")
        self.tile_unnamed = self.stats.add_tile("Unnamed ids", "0", "found only in labels")
        lay.addWidget(self.stats)

        self.warn_banner = Banner("", "warn")
        self.warn_banner.setVisible(False)
        lay.addWidget(self.warn_banner)

        table_card = Card("Categories", "double-click an id or a name to change it")
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["COLOR", "ID", "CLASS NAME", "COUNT", "SHARE", "MODIFY"])
        h = self.table.horizontalHeader()
        for col, w in ((0, 92), (1, 54), (3, 84), (5, 170)):
            h.setSectionResizeMode(col, QHeaderView.Fixed)
            self.table.setColumnWidth(col, w)
        # Names are short, so letting CLASS NAME take the slack left a huge
        # empty gap before COUNT. Give it a sane width you can still drag, and
        # let SHARE absorb the extra - a longer meter is easier to read anyway.
        h.setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.setColumnWidth(2, 176)
        h.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.setShowGrid(False)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setMinimumHeight(220)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Header labels default to centred, which left the "CLASS NAME"
        # caption floating in the middle of a stretch column while the names
        # underneath sat hard left. Match each header to its cells.
        header_align = {
            0: Qt.AlignCenter,
            1: Qt.AlignCenter,
            2: Qt.AlignLeft | Qt.AlignVCenter,
            3: Qt.AlignRight | Qt.AlignVCenter,
            4: Qt.AlignLeft | Qt.AlignVCenter,
            5: Qt.AlignCenter,
        }
        for col, align in header_align.items():
            item = self.table.horizontalHeaderItem(col)
            if item is not None:
                item.setTextAlignment(align)

        self.table.cellDoubleClicked.connect(self._on_double_click)
        table_card.body.addWidget(self.table)
        lay.addWidget(table_card, stretch=1)

        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

        self.status = StatusBar()
        root.addWidget(self.status)

    # ---------------------------------------------------------------- data
    def set_project(self, pm):
        self.pm = pm
        self.refresh()

    def refresh(self):
        if not self.pm:
            self.table.setRowCount(0)
            self.status.set_left("no project")
            return

        classes = self.pm.get_classes()
        counts: Dict[int, int] = {cid: 0 for cid, _, _ in classes}
        images_per: Dict[int, int] = {}
        annotated = total_boxes = 0

        for row in self.pm.get_images():
            lf = read_label_file(self.pm.label_path(row["filename"]))
            if not lf.boxes:
                continue
            annotated += 1
            total_boxes += len(lf.boxes)
            for cid in {b.class_id for b in lf.boxes}:
                images_per[cid] = images_per.get(cid, 0) + 1
            for b in lf.boxes:
                counts[b.class_id] = counts.get(b.class_id, 0) + 1

        known = {cid for cid, _, _ in classes}
        unnamed = sorted(cid for cid in counts if cid not in known)

        self.tile_classes.set_value(len(classes))
        self.tile_boxes.set_value(total_boxes)
        self.tile_images.set_value(annotated)
        self.tile_unnamed.set_value(len(unnamed),
                                    T.WARN if unnamed else T.TX_1)

        if unnamed:
            self.warn_banner.set_text(
                "Class id(s) <b>" + ", ".join(map(str, unnamed)) + "</b> appear in "
                "label files but have no name here. They export as "
                "<b>class&lt;id&gt;</b> in data.yaml — give them names below, or "
                "remap them on the Tools page.")
            self.warn_banner.setVisible(True)
        else:
            self.warn_banner.setVisible(False)

        rows = [(cid, name, col) for cid, name, col in classes]
        rows += [(cid, None, class_color(cid)) for cid in unnamed]

        query = self.search.text().strip().lower()
        if query:
            rows = [r for r in rows
                    if query in (r[1] or f"class{r[0]}").lower() or query == str(r[0])]

        mode = self.sort_combo.currentIndex()
        if mode == 1:
            rows.sort(key=lambda r: (r[1] or f"class{r[0]}").lower())
        elif mode == 2:
            rows.sort(key=lambda r: counts.get(r[0], 0), reverse=True)
        elif mode == 3:
            rows.sort(key=lambda r: counts.get(r[0], 0))
        else:
            rows.sort(key=lambda r: r[0])

        self.count_lbl.setText(
            f"{len(rows)} of {len(classes) + len(unnamed)} shown" if query
            else f"{len(classes) + len(unnamed)} class(es)")

        self.table.setRowCount(len(rows))
        for i, (cid, name, color_hex) in enumerate(rows):
            n = counts.get(cid, 0)

            col_btn = ghost_button("", "Change colour", size="sm")
            col_btn.setIcon(dot(color_hex, 13))
            col_btn.setFixedWidth(34)
            col_btn.clicked.connect(lambda _=False, c=cid: self._pick_color(c))
            self.table.setCellWidget(i, 0, self._center(col_btn))

            id_item = QTableWidgetItem(str(cid))
            id_item.setTextAlignment(Qt.AlignCenter)
            id_item.setFont(mono_font(T.FS_CONTROL))
            id_item.setForeground(QColor(T.TX_3))
            id_item.setFlags(Qt.ItemIsEnabled)
            id_item.setToolTip("Double-click to renumber this class")
            self.table.setItem(i, 1, id_item)

            name_item = QTableWidgetItem(name if name else f"class{cid}")
            name_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            name_item.setForeground(QColor(T.TX_1 if name else T.WARN))
            name_item.setFlags(Qt.ItemIsEnabled)
            if not name:
                name_item.setToolTip("Only found in label files — not named yet")
            self.table.setItem(i, 2, name_item)

            cnt_item = QTableWidgetItem(f"{n:,}")
            cnt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            cnt_item.setFont(mono_font(T.FS_CONTROL))
            cnt_item.setForeground(QColor(T.TX_2 if n else T.TX_4))
            cnt_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(i, 3, cnt_item)

            share = QWidget()
            sl = QHBoxLayout(share)
            sl.setContentsMargins(0, 0, T.S3, 0)
            sl.setSpacing(T.S2)
            meter = Meter(color_hex, (n / total_boxes) if total_boxes else 0)
            sl.addWidget(meter, stretch=1)
            pct = mono_label(f"{(n / total_boxes * 100) if total_boxes else 0:4.1f}%",
                             T.FS_SMALL, T.TX_3)
            pct.setFixedWidth(44)
            pct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            sl.addWidget(pct)
            self.table.setCellWidget(i, 4, share)

            acts = QWidget()
            al = QHBoxLayout(acts)
            al.setContentsMargins(0, 0, T.S2, 0)
            al.setSpacing(T.S1)
            al.addStretch()
            if name is None:
                nm_btn = button("Name it", size="sm")
                nm_btn.clicked.connect(lambda _=False, c=cid: self._name_unnamed(c))
                al.addWidget(nm_btn)
            else:
                r_btn = ghost_button("Rename", size="sm")
                r_btn.clicked.connect(
                    lambda _=False, c=cid, nm=name: self._rename_class(c, nm))
                d_btn = danger_button("", "Delete this category", "trash", "sm")
                d_btn.clicked.connect(
                    lambda _=False, c=cid, nm=name, k=n: self._delete_class(c, nm, k))
                al.addWidget(r_btn)
                al.addWidget(d_btn)
            self.table.setCellWidget(i, 5, acts)

        self.status.set_left(
            f"{len(classes)} named · {len(unnamed)} unnamed",
            T.WARN if unnamed else T.TX_3)
        self.status.set_right(f"{total_boxes:,} boxes in {annotated:,} images")

    @staticmethod
    def _center(w: QWidget) -> QWidget:
        holder = QWidget()
        lay = QHBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignCenter)
        lay.addWidget(w)
        return holder

    def _on_double_click(self, row: int, col: int):
        if col not in (1, 2):
            return
        item = self.table.item(row, 2)
        id_item = self.table.item(row, 1)
        if not item or not id_item:
            return
        cid = int(id_item.text())
        known = {c[0] for c in self.pm.get_classes()}
        if col == 1:
            self._change_class_id(cid, item.text())
        elif cid in known:
            self._rename_class(cid, item.text())
        else:
            self._name_unnamed(cid)

    # ------------------------------------------------------------- actions
    def _add_class(self):
        if not self.pm:
            return
        name, ok = QInputDialog.getText(self, "Add class", "Category name:")
        if ok and name.strip():
            self.pm.add_class(name.strip())
            self.refresh()
            self.classesUpdated.emit()

    def _name_unnamed(self, class_id: int):
        name, ok = QInputDialog.getText(
            self, f"Name class {class_id}",
            f"Class id {class_id} appears in your labels.\nWhat is it?",
            text=f"class{class_id}")
        if ok and name.strip():
            self.pm.ensure_class(class_id, name.strip())
            self.pm.rename_class(class_id, name.strip())
            self.refresh()
            self.classesUpdated.emit()

    def _pick_color(self, class_id: int):
        if not self.pm:
            return
        current = dict((cid, col) for cid, _, col in self.pm.get_classes())
        col = QColorDialog.getColor(
            QColor(current.get(class_id, class_color(class_id))), self,
            "Class colour")
        if col.isValid():
            self.pm.ensure_class(class_id)
            self.pm.update_class_color(class_id, col.name())
            self.refresh()
            self.classesUpdated.emit()

    def _rename_class(self, class_id: int, current_name: str):
        name, ok = QInputDialog.getText(self, "Rename class", "New name:",
                                        text=current_name)
        if ok and name.strip() and name.strip() != current_name:
            self.pm.rename_class(class_id, name.strip())
            self.refresh()
            self.classesUpdated.emit()

    def _change_class_id(self, old_id: int, name: str):
        """
        Renumber a class. The id is what actually lives in every label file, so
        this rewrites them all; there is no undo for that.
        """
        new_id, ok = QInputDialog.getInt(
            self, "Change class id",
            f"New id for “{name}”:\n\n"
            f"Every label file using id {old_id} is rewritten.",
            value=old_id, min=0, max=999)
        if not ok or new_id == old_id:
            return

        named = {cid: (nm, col) for cid, nm, col in self.pm.get_classes()}
        in_labels = self._ids_in_labels()
        occupied = new_id in named or new_id in in_labels
        boxes_moving = self._boxes_using(old_id)

        if occupied:
            other = named.get(new_id, (f"class{new_id}", ""))[0]
            other_boxes = self._boxes_using(new_id)
            box = QMessageBox(self)
            box.setWindowTitle("Id already in use")
            box.setIcon(QMessageBox.Warning)
            box.setTextFormat(Qt.RichText)
            box.setText(f"Id <b>{new_id}</b> already belongs to "
                        f"<b>{other}</b>.")
            box.setInformativeText(
                f"Swap them instead?<br><br>"
                f"<b>{name}</b> {old_id} &rarr; {new_id} "
                f"({boxes_moving:,} boxes)<br>"
                f"<b>{other}</b> {new_id} &rarr; {old_id} "
                f"({other_boxes:,} boxes)<br><br>"
                f"Label files are rewritten in place. "
                f"<b>This cannot be undone.</b>")
            swap_btn = box.addButton("Swap", QMessageBox.DestructiveRole)
            box.addButton("Cancel", QMessageBox.RejectRole)
            box.setDefaultButton(box.buttons()[-1])
            box.exec()
            if box.clickedButton() is not swap_btn:
                return
            mapping = {old_id: new_id, new_id: old_id}
        else:
            box = QMessageBox(self)
            box.setWindowTitle("Change class id")
            box.setIcon(QMessageBox.Warning)
            box.setTextFormat(Qt.RichText)
            box.setText(f"Renumber <b>{name}</b> from {old_id} to {new_id}?")
            box.setInformativeText(
                f"{boxes_moving:,} box(es) will be rewritten across your label "
                f"files.<br><br><b>This cannot be undone.</b>")
            go = box.addButton("Renumber", QMessageBox.DestructiveRole)
            box.addButton("Cancel", QMessageBox.RejectRole)
            box.setDefaultButton(box.buttons()[-1])
            box.exec()
            if box.clickedButton() is not go:
                return
            mapping = {old_id: new_id}

        from core.dataset_source import DatasetSource
        from core import labelops as ops
        res = ops.remap_classes(DatasetSource(self.pm.root), mapping, dry_run=False)
        changed = res.boxes_changed + self._remap_in_dir(
            self.pm.aug_labels_dir, mapping)

        # move the class rows to match what the labels now say
        old_meta = named.get(old_id, (name, class_color(old_id)))
        new_meta = named.get(new_id)
        for cid in {old_id, new_id} & set(named):
            self.pm.delete_class(cid)
        self.pm.ensure_class(new_id, old_meta[0])
        self.pm.rename_class(new_id, old_meta[0])
        self.pm.update_class_color(new_id, old_meta[1])
        if occupied and new_meta:
            self.pm.ensure_class(old_id, new_meta[0])
            self.pm.rename_class(old_id, new_meta[0])
            self.pm.update_class_color(old_id, new_meta[1])

        self.refresh()
        self.classesUpdated.emit()
        self.status.set_left(
            f"renumbered {changed:,} box(es) " +
            (f"({old_id} ⇄ {new_id})" if occupied
             else f"({old_id} → {new_id})"), T.OK)

    def _ids_in_labels(self) -> set:
        ids = set()
        for row in self.pm.get_images():
            for b in read_label_file(self.pm.label_path(row["filename"])).boxes:
                ids.add(b.class_id)
        return ids

    def _boxes_using(self, class_id: int) -> int:
        n = 0
        for row in self.pm.get_images():
            n += sum(1 for b in read_label_file(self.pm.label_path(row["filename"])).boxes
                     if b.class_id == class_id)
        return n

    @staticmethod
    def _remap_in_dir(labels_dir, mapping: Dict[int, int]) -> int:
        """Apply a class-id mapping to a flat folder of labels (augmented/)."""
        from core.annotation import read_label_file as _read, save_yolo_annotations
        if not labels_dir or not labels_dir.is_dir():
            return 0
        changed = 0
        for path in labels_dir.glob("*.txt"):
            lf = _read(path)
            hit = False
            for b in lf.boxes:
                if b.class_id in mapping:
                    b.class_id = mapping[b.class_id]
                    changed += 1
                    hit = True
            if hit:
                save_yolo_annotations(path, lf.boxes)
        return changed

    def _delete_class(self, class_id: int, name: str, box_count: int):
        """Remove the category and every box that uses it. Not recoverable."""
        if box_count:
            images_hit = self._images_using(class_id)
            emptied = self._images_emptied_by(class_id)
            parts = [
                f"This will also delete <b>{box_count:,} box(es)</b> from your "
                f"label files.",
                f"{images_hit:,} label file(s) will be rewritten.",
            ]
            if emptied:
                parts.append(
                    f"{emptied:,} image(s) will be left with no boxes at all — "
                    f"they stay in the dataset as unlabelled.")
            parts.append("Label files are rewritten in place. "
                         "<b>This cannot be undone.</b>")
            detail = "<br><br>".join(parts)
        else:
            detail = "No boxes use this id, so only the category is removed."

        box = QMessageBox(self)
        box.setWindowTitle("Delete class permanently")
        box.setIcon(QMessageBox.Warning)
        box.setTextFormat(Qt.RichText)
        box.setText(f"Delete the category <b>{name}</b> (id {class_id})?")
        box.setInformativeText(detail)
        delete_btn = box.addButton("Delete permanently", QMessageBox.DestructiveRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.setDefaultButton(box.buttons()[-1])
        box.exec()
        if box.clickedButton() is not delete_btn:
            return

        removed = 0
        if box_count:
            from core.dataset_source import DatasetSource
            from core import labelops as ops
            src = DatasetSource(self.pm.root)
            res = ops.delete_class(src, class_id, dry_run=False)
            removed = res.boxes_changed
            # augmented labels live outside the DatasetSource layout
            removed += self._purge_from_dir(self.pm.aug_labels_dir, class_id)

        self.pm.delete_class(class_id)
        self.pm._sync_existing_files()
        self.refresh()
        self.classesUpdated.emit()
        self.status.set_left(
            f"deleted “{name}” and {removed:,} box(es)" if removed
            else f"deleted “{name}”", T.OK)

    def _images_using(self, class_id: int) -> int:
        n = 0
        for row in self.pm.get_images():
            lf = read_label_file(self.pm.label_path(row["filename"]))
            if any(b.class_id == class_id for b in lf.boxes):
                n += 1
        return n

    def _images_emptied_by(self, class_id: int) -> int:
        n = 0
        for row in self.pm.get_images():
            lf = read_label_file(self.pm.label_path(row["filename"]))
            if lf.boxes and all(b.class_id == class_id for b in lf.boxes):
                n += 1
        return n

    @staticmethod
    def _purge_from_dir(labels_dir, class_id: int) -> int:
        """Strip a class from a flat folder of label files (e.g. augmented/)."""
        from core.annotation import read_label_file as _read, save_yolo_annotations
        if not labels_dir or not labels_dir.is_dir():
            return 0
        removed = 0
        for path in labels_dir.glob("*.txt"):
            lf = _read(path)
            keep = [b for b in lf.boxes if b.class_id != class_id]
            if len(keep) != len(lf.boxes):
                removed += len(lf.boxes) - len(keep)
                save_yolo_annotations(path, keep)
        return removed

    def _reindex(self):
        if not self.pm:
            return
        classes = self.pm.get_classes()
        ids = [c[0] for c in classes]
        if ids == list(range(len(ids))):
            QMessageBox.information(self, "Nothing to do",
                                    "Class ids are already 0 to "
                                    f"{len(ids) - 1} with no gaps.")
            return
        mapping = {old: new for new, old in enumerate(ids)}
        preview = "\n".join(f"    {o} → {n}" for o, n in sorted(mapping.items())
                            if o != n)
        if QMessageBox.question(
                self, "Close gaps in class ids",
                f"Renumber classes and rewrite every label file:\n\n{preview}\n\n"
                "Label files are rewritten in place — this cannot be undone.\n\n"
                "Continue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return

        from core.dataset_source import DatasetSource
        from core import labelops as ops
        src = DatasetSource(self.pm.root)
        res = ops.remap_classes(src, mapping, dry_run=False)

        names = {cid: nm for cid, nm, _ in classes}
        colors = {cid: col for cid, _, col in classes}
        for cid in ids:
            self.pm.delete_class(cid)
        for old, new in sorted(mapping.items(), key=lambda kv: kv[1]):
            self.pm.ensure_class(new, names.get(old, f"class{new}"))
            self.pm.rename_class(new, names.get(old, f"class{new}"))
            self.pm.update_class_color(new, colors.get(old, class_color(new)))

        self.refresh()
        self.classesUpdated.emit()
        self.status.set_left(
            f"renumbered {res.boxes_changed:,} boxes in {res.files_changed:,} files",
            T.OK)
