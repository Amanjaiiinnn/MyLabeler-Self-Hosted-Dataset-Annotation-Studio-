"""
ui/health_view.py — Dataset Health page.

Replaces check_images_labels.py, delete-and-cleanup_unpaired_files.py and
find-empty-file.py with one scan that shows every problem at once, previews the
fix before touching anything, and routes deletions through .trash/ so a wrong
click is recoverable.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QProgressBar, QSizePolicy,
)

from core import labelops as ops
from core.trash import Trash
from core.workers import FunctionWorker
from ui.widgets import (
    AMBER_TEXT, MUTED, Card, DatasetPicker, LogPane, StatTile,
    danger_button, ghost_button, page_title, primary_button, check,
)

FIX_KEYS = ["unpaired", "empty", "malformed", "range"]


class HealthView(QWidget):
    """Scan, preview, fix. Nothing is deleted without a dry run being shown first."""

    datasetChanged = Signal()
    problemsFound = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        pass  # styled by ui/theme.py
        self.pm = None
        self.report: Optional[ops.AuditReport] = None
        self._worker = None
        self._source = None

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        pass
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 22, 32, 22)
        layout.setSpacing(16)

        # ── header ────────────────────────────────────────────
        head = QHBoxLayout()
        head.addWidget(page_title(
            "Dataset Health",
            "Find orphaned files, empty labels and broken annotations — then fix "
            "them in bulk. Deletions go to .trash/ and can be undone."), stretch=1)
        self.btn_scan = primary_button("Scan Dataset", "Full audit of the selected dataset")
        self.btn_scan.clicked.connect(self.run_scan)
        head.addWidget(self.btn_scan, alignment=Qt.AlignTop)
        layout.addLayout(head)

        # ── source picker ─────────────────────────────────────
        self.picker = DatasetPicker()
        self.picker.sourceChanged.connect(self._on_source_changed)
        layout.addWidget(self.picker)

        self.deep_chk = check("Also open every image to catch truncated files (slower)")
        layout.addWidget(self.deep_chk)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        pass  # styled by ui/theme.py
        layout.addWidget(self.progress)

        # ── stats ─────────────────────────────────────────────
        stats = QHBoxLayout()
        stats.setSpacing(26)
        self.tile_images = StatTile("Images", "0", "in this dataset")
        self.tile_boxes = StatTile("Annotations", "0", "boxes and polygons")
        self.tile_classes = StatTile("Class ids", "0", "present in labels")
        self.tile_problems = StatTile("Problems", "0", "fixable in bulk")
        for t in (self.tile_images, self.tile_boxes, self.tile_classes, self.tile_problems):
            stats.addWidget(t)
        stats.addStretch()
        layout.addLayout(stats)

        # ── problems table ────────────────────────────────────
        prob_card = Card("Problems found",
                         "Tick what you want to fix, preview it, then apply.")
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Fix", "Problem", "Count", "What fixing does"])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 50)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(2, 90)
        h.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(3, 300)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setFixedHeight(230)
        pass  # styled by ui/theme.py
        prob_card.body.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.btn_preview = ghost_button("Preview (dry run)",
                                        "List exactly what would change, without changing it")
        self.btn_preview.clicked.connect(lambda: self._apply(dry_run=True))
        self.btn_apply = danger_button("Apply Selected Fixes")
        self.btn_apply.clicked.connect(lambda: self._apply(dry_run=False))
        self.btn_select_all = ghost_button("Select all")
        self.btn_select_all.clicked.connect(self._select_all)
        btn_row.addWidget(self.btn_select_all)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_preview)
        btn_row.addWidget(self.btn_apply)
        prob_card.body.addLayout(btn_row)
        layout.addWidget(prob_card)

        # ── class distribution ────────────────────────────────
        dist_card = Card("Class distribution", "Boxes and images per class id.")
        self.dist_table = QTableWidget()
        self.dist_table.setColumnCount(4)
        self.dist_table.setHorizontalHeaderLabels(
            ["Class", "Name", "Boxes", "Images"])
        dh = self.dist_table.horizontalHeader()
        dh.setSectionResizeMode(0, QHeaderView.Fixed)
        self.dist_table.setColumnWidth(0, 80)
        dh.setSectionResizeMode(1, QHeaderView.Stretch)
        dh.setSectionResizeMode(2, QHeaderView.Fixed)
        self.dist_table.setColumnWidth(2, 110)
        dh.setSectionResizeMode(3, QHeaderView.Fixed)
        self.dist_table.setColumnWidth(3, 110)
        self.dist_table.verticalHeader().setVisible(False)
        self.dist_table.setShowGrid(False)
        pass
        self.dist_table.setMinimumHeight(160)
        dist_card.body.addWidget(self.dist_table)
        layout.addWidget(dist_card)

        # ── trash ─────────────────────────────────────────────
        trash_card = Card("Trash", "Everything this app deletes lands here first.")
        trash_row = QHBoxLayout()
        self.trash_lbl = QLabel("Trash is empty")
        self.trash_lbl.setObjectName("Muted")
        trash_row.addWidget(self.trash_lbl, stretch=1)
        self.btn_undo = primary_button("Undo Last Delete")
        self.btn_undo.clicked.connect(self._undo)
        self.btn_empty = danger_button("Empty Trash Permanently")
        self.btn_empty.clicked.connect(self._empty_trash)
        trash_row.addWidget(self.btn_undo)
        trash_row.addWidget(self.btn_empty)
        trash_card.body.addLayout(trash_row)
        layout.addWidget(trash_card)

        # ── output log ────────────────────────────────────────
        log_card = Card("Output")
        self.log = LogPane()
        self.log.setMinimumHeight(160)
        self.log.setPlainText("Choose a dataset and press Scan Dataset.")
        log_card.body.addWidget(self.log)
        layout.addWidget(log_card)

        layout.addStretch()
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._set_busy(False)
        self._render_problems()

    # ---------------------------------------------------------------- setup
    def set_project(self, pm):
        self.pm = pm
        self.picker.set_project(pm)
        self.refresh_trash()

    def refresh(self):
        self.picker.refresh()
        self.refresh_trash()

    def _on_source_changed(self):
        self.picker.refresh()
        self.report = None
        self._render_problems()
        self.refresh_trash()
        self.log.setPlainText("Dataset changed — press Scan Dataset.")

    def _current_trash(self) -> Optional[Trash]:
        src = self.picker.current_source()
        return Trash(src.root) if src else None

    # ----------------------------------------------------------- scanning
    def run_scan(self):
        src = self.picker.current_source()
        if not src or not src.is_valid:
            QMessageBox.information(self, "No dataset",
                                    "Choose a project or a dataset folder first.")
            return
        self._source = src
        self._set_busy(True, "Scanning…")
        self._worker = FunctionWorker(
            ops.audit, src, self.picker.current_splits(),
            check_images=self.deep_chk.isChecked())
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_scan_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, done: int, total: int):
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(done)

    def _on_scan_done(self, report: ops.AuditReport):
        self.report = report
        self._set_busy(False)
        self._render_problems()
        self._render_distribution()
        self.refresh_trash()

        lines = [f"Scanned {report.total_images:,} images "
                 f"({report.total_boxes:,} annotations, "
                 f"{len(report.class_counts)} class ids in use)."]
        if report.polygon_boxes:
            lines.append(f"{report.polygon_boxes:,} of them are OBB / polygon annotations.")
        if report.per_split and list(report.per_split) != [""]:
            lines.append("Per split: " + ", ".join(
                f"{k or 'all'}={v:,}" for k, v in report.per_split.items()))
        if report.multiclass_images:
            lines.append(f"{len(report.multiclass_images):,} images contain more than "
                         f"one class (reviewable on the Review page).")
        lines.append("")
        if report.problem_count == 0:
            lines.append("No problems found. This dataset is clean.")
        else:
            lines.append(f"{report.problem_count:,} problem(s) found — tick the ones "
                         f"to fix, then Preview.")
            for pair, bad in report.malformed_labels[:15]:
                lines.append(f"  malformed: {pair.label.name} -> {bad[0][:60]}")
        self.log.show_lines(lines)
        self.problemsFound.emit(report.problem_count)
        self.datasetChanged.emit()

    def _on_failed(self, msg: str):
        self._set_busy(False)
        QMessageBox.critical(self, "Scan failed", msg)

    def _set_busy(self, busy: bool, text: str = ""):
        self.progress.setVisible(busy)
        if busy:
            self.progress.setFormat(f"{text} %p%")
            self.progress.setValue(0)
        for w in (self.btn_scan, self.btn_preview, self.btn_apply, self.picker):
            w.setEnabled(not busy)

    # ---------------------------------------------------------- rendering
    def _render_problems(self):
        rows = self.report.summary_rows() if self.report else [
            ("Images with no label file", 0, "Move the image to .trash"),
            ("Label files with no image", 0, "Move the label to .trash"),
            ("Empty label files (0 boxes)", 0, "Move image + label to .trash"),
            ("Label files with unparseable lines", 0, "Rewrite the file, dropping bad lines"),
            ("Boxes with coords outside 0-1", 0, "Clamp coordinates into range"),
            ("Images that cannot be opened", 0, "Move image + label to .trash"),
        ]
        self.table.setRowCount(len(rows))
        self._checks = []
        for i, (name, count, fix) in enumerate(rows):
            cb = check("")
            cb.setEnabled(count > 0)
            holder = QWidget()
            hl = QHBoxLayout(holder)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setAlignment(Qt.AlignCenter)
            hl.addWidget(cb)
            self.table.setCellWidget(i, 0, holder)
            self._checks.append(cb)

            name_item = QTableWidgetItem(name)
            name_item.setFlags(Qt.ItemIsEnabled)
            name_item.setForeground(QColor("#ffffff" if count else "#6b7280"))
            self.table.setItem(i, 1, name_item)

            cnt_item = QTableWidgetItem(f"{count:,}")
            cnt_item.setTextAlignment(Qt.AlignCenter)
            cnt_item.setFlags(Qt.ItemIsEnabled)
            cnt_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            cnt_item.setForeground(QColor("#f87171" if count else "#4ade80"))
            self.table.setItem(i, 2, cnt_item)

            fix_item = QTableWidgetItem(fix)
            fix_item.setFlags(Qt.ItemIsEnabled)
            fix_item.setForeground(QColor("#9ca3af"))
            self.table.setItem(i, 3, fix_item)

        if self.report:
            self.tile_images.set_value(self.report.total_images)
            self.tile_boxes.set_value(self.report.total_boxes)
            self.tile_classes.set_value(len(self.report.class_counts))
            self.tile_problems.set_value(self.report.problem_count)
        has_problems = bool(self.report and self.report.problem_count)
        self.btn_preview.setEnabled(has_problems)
        self.btn_apply.setEnabled(has_problems)
        self.btn_select_all.setEnabled(has_problems)

    def _render_distribution(self):
        if not self.report:
            return
        src = self._source
        names = src.class_names() if src else {}
        ids = sorted(self.report.class_counts)
        self.dist_table.setRowCount(len(ids))
        for i, cid in enumerate(ids):
            id_item = QTableWidgetItem(f"[{cid}]")
            id_item.setTextAlignment(Qt.AlignCenter)
            id_item.setForeground(QColor(AMBER_TEXT))
            id_item.setFlags(Qt.ItemIsEnabled)
            self.dist_table.setItem(i, 0, id_item)

            nm = names.get(cid)
            name_item = QTableWidgetItem(nm or "— unnamed —")
            name_item.setFlags(Qt.ItemIsEnabled)
            name_item.setForeground(QColor("#ffffff" if nm else "#f87171"))
            self.dist_table.setItem(i, 1, name_item)

            for col, val in ((2, self.report.class_counts.get(cid, 0)),
                             (3, self.report.images_per_class.get(cid, 0))):
                it = QTableWidgetItem(f"{val:,}")
                it.setTextAlignment(Qt.AlignCenter)
                it.setFlags(Qt.ItemIsEnabled)
                it.setForeground(QColor("#d1d5db"))
                self.dist_table.setItem(i, col, it)

    def refresh_trash(self):
        trash = self._current_trash()
        if not trash:
            self.trash_lbl.setText("Trash is empty")
            self.btn_undo.setEnabled(False)
            self.btn_empty.setEnabled(False)
            return
        batches = trash.batches()
        total = sum(b.count for b in batches)
        if not batches:
            self.trash_lbl.setText("Trash is empty")
        else:
            mb = trash.size_bytes() / (1024 * 1024)
            last = batches[0]
            self.trash_lbl.setText(
                f"{total:,} file(s) in {len(batches)} batch(es), {mb:.1f} MB · "
                f"most recent: {last.count} file(s) — {last.reason or 'deleted'} "
                f"at {last.when}")
        self.btn_undo.setEnabled(bool(batches))
        self.btn_empty.setEnabled(bool(batches))

    def _select_all(self):
        for cb in self._checks:
            if cb.isEnabled():
                cb.setChecked(True)

    # -------------------------------------------------------------- fixing
    def _apply(self, dry_run: bool):
        if not self.report:
            return
        src = self._source or self.picker.current_source()
        trash = Trash(src.root)
        picked = [cb.isChecked() for cb in self._checks]
        if not any(picked):
            QMessageBox.information(self, "Nothing selected",
                                    "Tick at least one problem to fix.")
            return

        if not dry_run:
            summary = "\n".join(
                f"  • {self.table.item(i, 1).text()} ({self.table.item(i, 2).text()})"
                for i, on in enumerate(picked) if on)
            answer = QMessageBox.question(
                self, "Apply fixes",
                f"Apply these fixes to {src.label}?\n\n{summary}\n\n"
                "Deleted files move to .trash/ and can be undone.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return

        lines = [("DRY RUN — nothing was changed" if dry_run
                  else "APPLIED") + f" · {src.label}", ""]
        trashed = rewritten = 0

        # 0/1 -> unpaired images / labels, 2 -> empty, 3 -> malformed, 4 -> range,
        # 5 -> unreadable images
        if picked[0] or picked[1]:
            r = ops.fix_unpaired(src, self.report, trash,
                                 drop_images=picked[0], drop_labels=picked[1],
                                 dry_run=dry_run)
            trashed += r.trashed
            lines += r.details
        if picked[2]:
            r = ops.fix_empty_labels(src, self.report, trash, dry_run=dry_run)
            trashed += r.trashed
            lines += r.details
        if picked[3]:
            r = ops.fix_malformed_labels(src, self.report, dry_run=dry_run)
            rewritten += r.rewritten
            lines += r.details
        if picked[4]:
            r = ops.fix_out_of_range(src, self.report, dry_run=dry_run)
            rewritten += r.rewritten
            lines += r.details
        if picked[5] and self.report.unreadable_images:
            victims = []
            for p in self.report.unreadable_images:
                victims += [q for q in (p.image, p.label) if q and q.exists()]
                lines.append(f"unreadable image: {p.stem}")
            if not dry_run:
                trashed += trash.send(victims, reason="unreadable images").count
            else:
                trashed += len(victims)

        lines += ["", f"{'Would move' if dry_run else 'Moved'} {trashed:,} file(s) to .trash/",
                  f"{'Would rewrite' if dry_run else 'Rewrote'} {rewritten:,} label file(s)"]
        self.log.show_lines(lines)

        if not dry_run:
            src.refresh()
            if self.pm and src.root == self.pm.root:
                self.pm._sync_existing_files()
            self.refresh_trash()
            self.datasetChanged.emit()
            self.run_scan()

    def _undo(self):
        trash = self._current_trash()
        if not trash:
            return
        batch = trash.last_batch()
        if not batch:
            return
        if QMessageBox.question(
                self, "Undo delete",
                f"Restore {batch.count} file(s) deleted at {batch.when}?",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        n = trash.restore(batch)
        if self.pm:
            self.pm._sync_existing_files()
        self.refresh_trash()
        self.log.show_lines([f"Restored {n} file(s) from the trash."])
        self.datasetChanged.emit()
        self.run_scan()

    def _empty_trash(self):
        trash = self._current_trash()
        if not trash:
            return
        batches = trash.batches()
        total = sum(b.count for b in batches)
        if QMessageBox.warning(
                self, "Empty trash permanently",
                f"Permanently delete {total:,} file(s) in {len(batches)} batch(es)?\n\n"
                "This cannot be undone.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        n = trash.empty()
        self.refresh_trash()
        self.log.show_lines([f"Permanently removed {n} trash batch(es)."])
