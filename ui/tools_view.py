"""
ui/tools_view.py — Dataset Tools page.

Class tools replace change-class.py and test.py; subset tools replace
random_sample.py, image_output_range.py and split_dataset.py; the publish card
replaces roboflow_upload.py. Every destructive action previews first.
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QMessageBox,
    QFileDialog, QProgressBar, QGridLayout, QStackedWidget, QLineEdit,
)

from core import labelops as ops
from core.config import settings
from core.workers import FunctionWorker
from ui.widgets import (
    AMBER_TEXT, MUTED, Card, DatasetPicker, LogPane, combo, check, line_edit,
    danger_button, ghost_button, page_title, primary_button, spin,
)

MODE_MERGE = 0
MODE_SWAP = 1
MODE_REMAP = 2
MODE_DELETE = 3

SUBSET_RANDOM = 0
SUBSET_RANGE = 1
SUBSET_CHUNK = 2
SUBSET_NONULL = 3


class ToolsView(QWidget):
    datasetChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        pass  # styled by ui/theme.py
        self.pm = None
        self._worker = None
        self._class_ids: List[int] = []

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        pass
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 22, 32, 22)
        layout.setSpacing(16)

        layout.addWidget(page_title(
            "Dataset Tools",
            "Bulk class edits, subset extraction and publishing — on the open "
            "project or any dataset folder on disk."))

        self.picker = DatasetPicker()
        self.picker.sourceChanged.connect(self._on_source_changed)
        layout.addWidget(self.picker)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        pass  # styled by ui/theme.py
        layout.addWidget(self.progress)

        layout.addWidget(self._build_class_card())
        layout.addWidget(self._build_subset_card())
        layout.addWidget(self._build_publish_card())

        log_card = Card("Output")
        self.log = LogPane()
        self.log.setMinimumHeight(150)
        self.log.setPlainText("Pick a dataset, choose a tool, then Preview.")
        log_card.body.addWidget(self.log)
        layout.addWidget(log_card)

        layout.addStretch()
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ═══════════════════════════════════════════════════ class tools card ══
    def _build_class_card(self) -> Card:
        card = Card("Class tools",
                    "Rewrite class ids across every label file. Box coordinates are "
                    "never touched.")

        row = QHBoxLayout()
        row.addWidget(QLabel("Operation:"))
        self.class_mode = combo([
            "Merge all classes into one",
            "Swap two classes",
            "Remap one class to another",
            "Delete all boxes of a class",
        ])
        self.class_mode.setMinimumWidth(240)
        self.class_mode.currentIndexChanged.connect(self._on_class_mode)
        row.addWidget(self.class_mode)
        row.addStretch()
        card.body.addLayout(row)

        self.class_args = QStackedWidget()
        self.class_args.setFixedHeight(46)

        # merge
        merge = QWidget()
        ml = QHBoxLayout(merge)
        ml.setContentsMargins(0, 6, 0, 0)
        ml.addWidget(QLabel("Every class becomes:"))
        self.merge_target = combo()
        self.merge_target.setMinimumWidth(200)
        ml.addWidget(self.merge_target)
        ml.addStretch()
        self.class_args.addWidget(merge)

        # swap
        swap = QWidget()
        sl = QHBoxLayout(swap)
        sl.setContentsMargins(0, 6, 0, 0)
        sl.addWidget(QLabel("Swap"))
        self.swap_a = combo()
        self.swap_a.setMinimumWidth(180)
        sl.addWidget(self.swap_a)
        sl.addWidget(QLabel("⇄"))
        self.swap_b = combo()
        self.swap_b.setMinimumWidth(180)
        sl.addWidget(self.swap_b)
        sl.addStretch()
        self.class_args.addWidget(swap)

        # remap
        remap = QWidget()
        rl = QHBoxLayout(remap)
        rl.setContentsMargins(0, 6, 0, 0)
        rl.addWidget(QLabel("Change"))
        self.remap_from = combo()
        self.remap_from.setMinimumWidth(180)
        rl.addWidget(self.remap_from)
        rl.addWidget(QLabel("→"))
        self.remap_to = combo()
        self.remap_to.setMinimumWidth(180)
        rl.addWidget(self.remap_to)
        rl.addStretch()
        self.class_args.addWidget(remap)

        # delete
        dele = QWidget()
        dl = QHBoxLayout(dele)
        dl.setContentsMargins(0, 6, 0, 0)
        dl.addWidget(QLabel("Remove every box of class:"))
        self.delete_target = combo()
        self.delete_target.setMinimumWidth(200)
        dl.addWidget(self.delete_target)
        dl.addStretch()
        self.class_args.addWidget(dele)

        card.body.addWidget(self.class_args)

        btns = QHBoxLayout()
        btns.addStretch()
        self.btn_class_preview = ghost_button("Preview")
        self.btn_class_preview.clicked.connect(lambda: self._run_class_op(dry_run=True))
        self.btn_class_apply = danger_button("Apply to Labels")
        self.btn_class_apply.clicked.connect(lambda: self._run_class_op(dry_run=False))
        btns.addWidget(self.btn_class_preview)
        btns.addWidget(self.btn_class_apply)
        card.body.addLayout(btns)
        return card

    def _on_class_mode(self, idx: int):
        self.class_args.setCurrentIndex(idx)

    # ═════════════════════════════════════════════════════ subset tools ══
    def _build_subset_card(self) -> Card:
        card = Card("Subset & split",
                    "Copy a slice of the dataset into a new folder. Originals are "
                    "never modified.")

        row = QHBoxLayout()
        row.addWidget(QLabel("Extract:"))
        self.subset_mode = combo([
            "Random sample of N images",
            "Range of images (Nth to Mth)",
            "Sequential chunks of N (for batch upload)",
            "Only images that have annotations",
        ])
        self.subset_mode.setMinimumWidth(300)
        self.subset_mode.currentIndexChanged.connect(
            lambda i: self.subset_args.setCurrentIndex(i))
        row.addWidget(self.subset_mode)
        row.addStretch()
        card.body.addLayout(row)

        self.subset_args = QStackedWidget()
        self.subset_args.setFixedHeight(46)

        rand = QWidget()
        rl = QHBoxLayout(rand)
        rl.setContentsMargins(0, 6, 0, 0)
        rl.addWidget(QLabel("How many:"))
        self.rand_count = spin(1, 10_000_000, 500)
        rl.addWidget(self.rand_count)
        rl.addWidget(QLabel("Seed (blank = different every run):"))
        self.rand_seed = line_edit("42")
        self.rand_seed.setFixedWidth(80)
        rl.addWidget(self.rand_seed)
        rl.addStretch()
        self.subset_args.addWidget(rand)

        rng = QWidget()
        gl = QHBoxLayout(rng)
        gl.setContentsMargins(0, 6, 0, 0)
        gl.addWidget(QLabel("From #"))
        self.range_start = spin(1, 10_000_000, 1)
        gl.addWidget(self.range_start)
        gl.addWidget(QLabel("to #"))
        self.range_end = spin(1, 10_000_000, 300)
        gl.addWidget(self.range_end)
        gl.addWidget(QLabel("(1-based, inclusive, sorted by filename)"))
        gl.addStretch()
        self.subset_args.addWidget(rng)

        chunk = QWidget()
        cl = QHBoxLayout(chunk)
        cl.setContentsMargins(0, 6, 0, 0)
        cl.addWidget(QLabel("Images per chunk:"))
        self.chunk_size = spin(1, 100_000, 1500)
        cl.addWidget(self.chunk_size)
        self.chunk_hint = QLabel("")
        self.chunk_hint.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        self.chunk_size.valueChanged.connect(lambda _: self._update_chunk_hint())
        cl.addWidget(self.chunk_hint)
        cl.addStretch()
        self.subset_args.addWidget(chunk)

        nonull = QWidget()
        nl = QHBoxLayout(nonull)
        nl.setContentsMargins(0, 6, 0, 0)
        nl.addWidget(QLabel("Copies only images whose label file has at least one box."))
        nl.addStretch()
        self.subset_args.addWidget(nonull)

        card.body.addWidget(self.subset_args)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output folder:"))
        self.out_edit = line_edit("choose where the subset is written…")
        out_row.addWidget(self.out_edit, stretch=1)
        browse = ghost_button("Browse…")
        browse.clicked.connect(self._browse_output)
        out_row.addWidget(browse)
        card.body.addLayout(out_row)

        btns = QHBoxLayout()
        btns.addStretch()
        self.btn_subset = primary_button("Extract Subset")
        self.btn_subset.clicked.connect(self._run_subset)
        btns.addWidget(self.btn_subset)
        card.body.addLayout(btns)
        return card

    def _update_chunk_hint(self):
        src = self.picker.current_source()
        if not src:
            return
        n = len(src.pairs(self.picker.current_splits()))
        size = self.chunk_size.value()
        chunks = (n + size - 1) // size if size else 0
        self.chunk_hint.setText(f"→ {chunks} chunk folder(s) from {n:,} images")

    def _browse_output(self):
        start = settings().get("last_output_dir") or ""
        path = QFileDialog.getExistingDirectory(self, "Choose output folder", start)
        if path:
            settings().set("last_output_dir", path)
            self.out_edit.setText(path)

    # ══════════════════════════════════════════════════════════ publish ══
    def _build_publish_card(self) -> Card:
        from core.roboflow_sync import is_available
        card = Card("Publish to Roboflow",
                    "Upload an exported dataset folder to a Roboflow project. "
                    "The API key is stored in settings.json, or read from the "
                    "ROBOFLOW_API_KEY environment variable.")

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        s = settings()

        grid.addWidget(QLabel("API key:"), 0, 0)
        self.rf_key = line_edit("paste your Roboflow API key", s.get("roboflow_api_key", ""))
        self.rf_key.setEchoMode(QLineEdit.Password)
        grid.addWidget(self.rf_key, 0, 1)

        grid.addWidget(QLabel("Workspace:"), 1, 0)
        self.rf_workspace = line_edit("your-workspace", s.get("roboflow_workspace", ""))
        grid.addWidget(self.rf_workspace, 1, 1)

        grid.addWidget(QLabel("Project:"), 2, 0)
        self.rf_project = line_edit("your-project", s.get("roboflow_project", ""))
        grid.addWidget(self.rf_project, 2, 1)

        grid.addWidget(QLabel("Dataset folder:"), 3, 0)
        folder_row = QHBoxLayout()
        self.rf_folder = line_edit("an exported dataset folder…")
        folder_row.addWidget(self.rf_folder, stretch=1)
        pick = ghost_button("Browse…")
        pick.clicked.connect(self._browse_upload_folder)
        folder_row.addWidget(pick)
        holder = QWidget()
        holder.setLayout(folder_row)
        grid.addWidget(holder, 3, 1)
        grid.setColumnStretch(1, 1)
        card.body.addLayout(grid)

        note = QLabel(
            "If you previously had a key hard-coded in roboflow_upload.py, rotate it"
            "at app.roboflow.com → Settings → API keys before reusing it here.")
        note.setWordWrap(True)
        pass  # styled by ui/theme.py
        card.body.addWidget(note)

        btns = QHBoxLayout()
        self.rf_status = QLabel("")
        self.rf_status.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        btns.addWidget(self.rf_status, stretch=1)
        save_btn = ghost_button("Save credentials")
        save_btn.clicked.connect(self._save_rf)
        self.btn_upload = primary_button("Upload to Roboflow")
        self.btn_upload.clicked.connect(self._upload)
        btns.addWidget(save_btn)
        btns.addWidget(self.btn_upload)
        card.body.addLayout(btns)

        if not is_available():
            self.btn_upload.setEnabled(False)
            self.rf_status.setText("roboflow package not installed — run: pip install roboflow")
        return card

    def _browse_upload_folder(self):
        start = str(self.pm.exports_dir) if self.pm else ""
        path = QFileDialog.getExistingDirectory(self, "Choose dataset to upload", start)
        if path:
            self.rf_folder.setText(path)

    def _save_rf(self):
        settings().update(
            roboflow_api_key=self.rf_key.text().strip(),
            roboflow_workspace=self.rf_workspace.text().strip(),
            roboflow_project=self.rf_project.text().strip())
        self.rf_status.setText("Saved to settings.json")

    def _upload(self):
        from core.roboflow_sync import RoboflowUploadWorker, UploadTarget
        target = UploadTarget(
            api_key=self.rf_key.text().strip() or settings().roboflow_api_key(),
            workspace=self.rf_workspace.text().strip(),
            project=self.rf_project.text().strip(),
            dataset_path=Path(self.rf_folder.text().strip()),
        )
        problems = target.problems()
        if problems:
            QMessageBox.warning(self, "Cannot upload", "\n".join(problems))
            return
        if QMessageBox.question(
                self, "Upload to Roboflow",
                f"Upload\n  {target.dataset_path}\nto {target.workspace}/{target.project}?\n\n"
                "This sends your images to Roboflow's servers.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self._set_busy(True, "Uploading…")
        self.progress.setMaximum(0)      # indeterminate
        self._worker = RoboflowUploadWorker(target)
        self._worker.finished_ok.connect(self._on_upload_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_upload_done(self, msg: str):
        self._set_busy(False)
        self.log.show_lines([msg])
        QMessageBox.information(self, "Upload complete", msg)

    # ═══════════════════════════════════════════════════════════ running ══
    def set_upload_folder(self, path: str):
        self.rf_folder.setText(path)

    def set_project(self, pm):
        self.pm = pm
        self.picker.set_project(pm)
        self.refresh()

    def refresh(self):
        self.picker.refresh()
        self._reload_classes()
        self._update_chunk_hint()

    def _on_source_changed(self):
        self.picker.refresh()
        self._reload_classes()
        self._update_chunk_hint()

    def _reload_classes(self):
        src = self.picker.current_source()
        if not src or not src.is_valid:
            self._class_ids = []
            return
        # ids actually present in the labels, plus any named ones
        names = src.class_names()
        present = set(names)
        for path in src.label_files(self.picker.current_splits())[:4000]:
            try:
                for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                    tok = line.split()
                    if tok:
                        try:
                            present.add(int(float(tok[0])))
                        except ValueError:
                            pass
            except OSError:
                continue
        self._class_ids = sorted(present)
        entries = [(cid, names.get(cid, f"class{cid}")) for cid in self._class_ids]
        for c in (self.merge_target, self.swap_a, self.swap_b, self.remap_from,
                  self.remap_to, self.delete_target):
            c.blockSignals(True)
            c.clear()
            for cid, nm in entries:
                c.addItem(f"[{cid}] {nm}", userData=cid)
            c.blockSignals(False)
        if len(entries) > 1:
            self.swap_b.setCurrentIndex(1)
            self.remap_to.setCurrentIndex(1)

    def _sel(self, box) -> Optional[int]:
        return box.currentData()

    def _run_class_op(self, dry_run: bool):
        src = self.picker.current_source()
        if not src or not src.is_valid:
            QMessageBox.information(self, "No dataset", "Choose a dataset first.")
            return
        if not self._class_ids:
            QMessageBox.information(self, "No classes",
                                    "No class ids were found in this dataset's labels.")
            return

        mode = self.class_mode.currentIndex()
        splits = self.picker.current_splits()

        if mode == MODE_DELETE:
            cid = self._sel(self.delete_target)
            desc = f"delete every box of class {cid}"
            fn, args = ops.delete_class, (src, cid, splits)
        else:
            if mode == MODE_MERGE:
                target = self._sel(self.merge_target)
                mapping = ops.merge_all_mapping(self._class_ids, target)
                desc = f"merge all classes into {target}"
            elif mode == MODE_SWAP:
                a, b = self._sel(self.swap_a), self._sel(self.swap_b)
                if a == b:
                    QMessageBox.information(self, "Pick two classes",
                                            "Choose two different classes to swap.")
                    return
                mapping = ops.swap_mapping(a, b)
                desc = f"swap class {a} and {b}"
            else:
                a, b = self._sel(self.remap_from), self._sel(self.remap_to)
                if a == b:
                    QMessageBox.information(self, "Pick two classes",
                                            "Source and target class are the same.")
                    return
                mapping = {a: b}
                desc = f"remap class {a} to {b}"
            fn, args = ops.remap_classes, (src, mapping, splits)

        if not dry_run:
            if QMessageBox.question(
                    self, "Rewrite labels",
                    f"This will {desc} across {src.label}.\n\n"
                    "Label files are rewritten in place — there is no undo for "
                    "class edits, so preview first if you have not.\n\nContinue?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return

        self._set_busy(True, "Rewriting labels…")
        self._pending = (dry_run, desc)
        self._worker = FunctionWorker(fn, *args, dry_run=dry_run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_class_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_class_done(self, res: ops.RemapResult):
        dry_run, desc = self._pending
        self._set_busy(False)
        verb = "Would change" if dry_run else "Changed"
        self.log.show_lines([
            ("DRY RUN — nothing was written" if dry_run else "APPLIED") + f" · {desc}",
            "",
            f"Scanned {res.files_scanned:,} label file(s)",
            f"{verb} {res.boxes_changed:,} box(es) in {res.files_changed:,} file(s)",
        ])
        if not dry_run:
            self._reload_classes()
            if self.pm:
                self.pm.sync_classes_from_labels()
            self.datasetChanged.emit()

    def _run_subset(self):
        src = self.picker.current_source()
        if not src or not src.is_valid:
            QMessageBox.information(self, "No dataset", "Choose a dataset first.")
            return
        out_text = self.out_edit.text().strip()
        if not out_text:
            QMessageBox.information(self, "No output folder",
                                    "Choose where the subset should be written.")
            return

        out = Path(out_text)
        mode = self.subset_mode.currentIndex()
        splits = self.picker.current_splits()

        try:
            if mode == SUBSET_RANDOM:
                seed_txt = self.rand_seed.text().strip()
                seed = int(seed_txt) if seed_txt.isdigit() else None
                out = out / f"random_{self.rand_count.value()}"
                fn = ops.random_sample
                args = (src, self.rand_count.value(), out, splits, seed)
            elif mode == SUBSET_RANGE:
                a, b = self.range_start.value(), self.range_end.value()
                out = out / f"range_{a}_{b}"
                fn, args = ops.copy_range, (src, a, b, out, splits)
            elif mode == SUBSET_CHUNK:
                out = out / f"chunks_{self.chunk_size.value()}"
                fn, args = ops.chunk_dataset, (src, self.chunk_size.value(), out, splits)
            else:
                out = out / "annotated_only"
                fn, args = ops.filter_null, (src, out, splits)
        except ValueError as e:
            QMessageBox.warning(self, "Invalid settings", str(e))
            return

        if out.exists() and any(out.iterdir()):
            if QMessageBox.question(
                    self, "Folder not empty",
                    f"{out} already has files in it. Write into it anyway?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return

        self._set_busy(True, "Copying…")
        self._worker = FunctionWorker(fn, *args)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_subset_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_subset_done(self, res: ops.SubsetResult):
        self._set_busy(False)
        lines = [f"Copied {res.copied:,} image(s) to:", f"  {res.output_dir}"]
        if res.chunks:
            lines.append("")
            lines.append(f"{len(res.chunks)} chunk folder(s):")
            lines += [f"  {c.name}" for c in res.chunks[:30]]
        if res.missing_labels:
            lines += ["", f"WARNING: {len(res.missing_labels):,} image(s) had no label file:"]
            lines += [f"  - {n}" for n in res.missing_labels[:20]]
        self.log.show_lines(lines)
        QMessageBox.information(self, "Subset ready",
                                f"Copied {res.copied:,} image(s) to\n{res.output_dir}")

    # ------------------------------------------------------------- helpers
    def _on_progress(self, done: int, total: int):
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(done)

    def _on_failed(self, msg: str):
        self._set_busy(False)
        self.log.show_lines([f"FAILED: {msg}"])
        QMessageBox.critical(self, "Operation failed", msg)

    def _set_busy(self, busy: bool, text: str = ""):
        self.progress.setVisible(busy)
        if busy:
            self.progress.setMaximum(1)
            self.progress.setValue(0)
            self.progress.setFormat(f"{text} %p%")
        for w in (self.btn_class_preview, self.btn_class_apply, self.btn_subset,
                  self.btn_upload, self.picker):
            w.setEnabled(not busy)
