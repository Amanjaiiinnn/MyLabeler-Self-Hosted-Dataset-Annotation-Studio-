"""
ui/main_window.py — the application shell.

There is no global header bar. The sidebar is the app's only chrome; every
action lives in the toolbar of the page it belongs to. Model loading and
auto-labelling used to sit in a top bar visible from every page, including the
ones where they did nothing — they now belong to Dataset and Annotate.
"""
from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QMessageBox, QStackedWidget,
    QFileDialog, QInputDialog, QProgressDialog,
)

from core.project import ProjectManager
from core.config import settings
from core.annotation import load_yolo_annotations
from core.workers import ModelLoadWorker, AutoLabelWorker, AugmentationWorker, ExportWorker
from core.yolo_predictor import DEFAULT_MODEL, YoloPredictor

from ui.theme import T, ThemeManager
from ui.sidebar import Sidebar
from ui.projects_view import ProjectsView
from ui.upload_view import UploadView
from ui.dataset_view import DatasetView
from ui.annotate_view import AnnotateView
from ui.versions_view import VersionsView
from ui.classes_view import ClassesView
from ui.review_view import ReviewView
from ui.health_view import HealthView
from ui.tools_view import ToolsView
from ui.autolabel_dialog import AutoLabelDialog
from ui.augmentation_dialog import AugmentationDialog
from ui.project_dialog import NewProjectDialog
from ui.export_dialog import ExportDialog

PROJECTS_ROOT = str(Path(__file__).resolve().parent.parent / "projects")

VIEW_INDEX = {
    "upload": 0, "annotate": 1, "dataset": 2, "versions": 3, "classes": 4,
    "review": 5, "health": 6, "tools": 7, "projects": 8,
}
# The rail stays expanded; collapsing is a manual choice (Ctrl+B).


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MyLabeler")
        self.resize(1560, 950)

        self.pm: ProjectManager | None = None
        self.predictor: YoloPredictor | None = None
        self._model_worker = None
        self._autolabel_worker = None
        self._aug_worker = None
        self._export_worker = None
        self._progress = None

        root_widget = QWidget()
        root_widget.setObjectName("Page")
        self.setCentralWidget(root_widget)
        root = QHBoxLayout(root_widget)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.navigationChanged.connect(self._on_navigation_changed)
        self.sidebar.openProjectRequested.connect(self._open_project)
        self.sidebar.newProjectRequested.connect(self._new_project)
        self.sidebar.trashRequested.connect(self._undo_last_delete)
        root.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        self.stack.setObjectName("Page")
        root.addWidget(self.stack, stretch=1)

        self._build_views()
        self._build_shortcuts()
        self._load_default_project()

    # ---------------------------------------------------------------- views
    def _build_views(self):
        self.upload_view = UploadView()
        self.upload_view.importFilesRequested.connect(self._import_images)
        self.upload_view.importFolderRequested.connect(self._import_folder)
        self.stack.addWidget(self.upload_view)                       # 0

        self.annotate_view = AnnotateView()
        self.annotate_view.backToDatasetRequested.connect(
            lambda: self._on_navigation_changed("dataset"))
        self.annotate_view.annotationsChanged.connect(self._on_annotations_changed)
        self.stack.addWidget(self.annotate_view)                     # 1

        self.dataset_view = DatasetView()
        self.dataset_view.openImageRequested.connect(self._open_image_in_annotator)
        self.dataset_view.autoLabelSelectedRequested.connect(
            lambda files: self._run_autolabel(scope="selected", target_files=files))
        self.dataset_view.autoLabelAllRequested.connect(
            lambda: self._run_autolabel(scope="unlabeled"))
        self.dataset_view.loadModelRequested.connect(self._load_model)
        self.dataset_view.deleteSelectedRequested.connect(self._on_images_deleted)
        self.dataset_view.exportRequested.connect(self._open_export_dialog)
        self.stack.addWidget(self.dataset_view)                      # 2

        self.versions_view = VersionsView()
        self.versions_view.labelImagesRequested.connect(
            lambda: self._run_autolabel(scope="unlabeled"))
        self.versions_view.generateAugmentationsRequested.connect(
            self._open_augmentation_dialog)
        self.versions_view.exportDatasetRequested.connect(self._export_version)
        self.stack.addWidget(self.versions_view)                     # 3

        self.classes_view = ClassesView()
        self.classes_view.classesUpdated.connect(self._on_classes_updated)
        self.stack.addWidget(self.classes_view)                      # 4

        self.review_view = ReviewView()
        self.review_view.datasetChanged.connect(self._on_dataset_mutated)
        self.review_view.openInAnnotatorRequested.connect(self._open_image_in_annotator)
        self.stack.addWidget(self.review_view)                       # 5

        self.health_view = HealthView()
        self.health_view.datasetChanged.connect(self._on_dataset_mutated)
        self.health_view.problemsFound.connect(self.sidebar.set_health_badge)
        self.stack.addWidget(self.health_view)                       # 6

        self.tools_view = ToolsView()
        self.tools_view.datasetChanged.connect(self._on_dataset_mutated)
        self.stack.addWidget(self.tools_view)                        # 7

        self.projects_view = ProjectsView(PROJECTS_ROOT)
        self.projects_view.projectOpened.connect(self._open_project_path)
        self.projects_view.newProjectRequested.connect(self._new_project)
        self.projects_view.openFolderRequested.connect(self._open_project)
        self.stack.addWidget(self.projects_view)                     # 8

    # ----------------------------------------------------------- shortcuts
    def _build_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._open_project)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._new_project)
        QShortcut(QKeySequence("Ctrl+I"), self,
                  activated=lambda: self._on_navigation_changed("upload"))
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._save_current)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self._undo_last_delete)
        QShortcut(QKeySequence("Ctrl+B"), self, activated=self.sidebar.toggle_collapsed)

        av = self.annotate_view

        def annotate_shortcut(key, fn):
            s = QShortcut(QKeySequence(key), av)
            s.setContext(Qt.WidgetWithChildrenShortcut)
            s.activated.connect(fn)
            return s

        annotate_shortcut("D", lambda: av.set_draw_mode(True))
        annotate_shortcut("V", lambda: av.set_draw_mode(False))
        annotate_shortcut("Escape", lambda: av.set_draw_mode(False))
        annotate_shortcut("Right", av._next_image)
        annotate_shortcut("Left", av._prev_image)
        annotate_shortcut("F", av.canvas.fit_to_view)
        annotate_shortcut("Ctrl+1", av.canvas.zoom_to_100)
        annotate_shortcut("Ctrl+Z", av.canvas.undo)
        annotate_shortcut("Ctrl+Y", av.canvas.redo)
        annotate_shortcut("Ctrl+D", av.canvas.duplicate_selected)
        annotate_shortcut("Delete", av.canvas.delete_selected)
        annotate_shortcut("Backspace", av.canvas.delete_selected)
        annotate_shortcut("L", av.canvas.toggle_lock_selected)
        for i in range(10):
            annotate_shortcut(str(i),
                              lambda idx=i: av.class_panel.select_class_by_index(idx))

    def _save_current(self):
        if self.stack.currentIndex() == VIEW_INDEX["annotate"]:
            self.annotate_view.save_current()

    # ----------------------------------------------------------- navigation
    def _on_navigation_changed(self, key: str):
        if key not in VIEW_INDEX:
            return
        self.sidebar.set_active(key)
        self.stack.setCurrentIndex(VIEW_INDEX[key])

        if key == "annotate":
            if not self.annotate_view.current_filename and self.pm:
                imgs = self.pm.get_images()
                if imgs:
                    self.annotate_view.load_image(imgs[0]["filename"])
            self.annotate_view.setFocus()
        elif key == "dataset":
            self.dataset_view.refresh()
        elif key == "versions":
            self.versions_view.refresh()
        elif key == "classes":
            self.classes_view.refresh()
        elif key == "review":
            self.review_view.refresh()
            self.review_view.setFocus()
        elif key == "health":
            self.health_view.refresh()
        elif key == "tools":
            self.tools_view.refresh()
        elif key == "projects":
            self.projects_view.refresh()

    def _open_image_in_annotator(self, filename: str):
        self.annotate_view.load_image(filename)
        self._on_navigation_changed("annotate")

    def _on_annotations_changed(self):
        self._refresh_sidebar()

    def _on_images_deleted(self, _files):
        self.dataset_view.refresh()
        self._refresh_sidebar()

    def _on_dataset_mutated(self):
        if not self.pm:
            return
        self.pm._sync_existing_files()
        self.pm.sync_classes_from_labels()
        self.dataset_view.set_project(self.pm)
        self.annotate_view.set_project(self.pm)
        self._refresh_sidebar()

    def _refresh_sidebar(self):
        if not self.pm:
            return
        stats = self.pm.stats()
        self.sidebar.set_project_info(self.pm.root.name, stats["total"])
        try:
            self.sidebar.set_trash_info(
                sum(b.count for b in self.pm.trash().batches()))
        except Exception:
            pass
        classes = self.pm.get_classes()
        self.sidebar.set_badge("classes", f"{len(classes)}" if classes else "")
        try:
            n_versions = len([p for p in self.pm.exports_dir.iterdir() if p.is_dir()])
            self.sidebar.set_badge("versions", f"{n_versions}" if n_versions else "")
        except OSError:
            pass

    # ----------------------------------------------------------- projects
    def _load_default_project(self):
        Path(PROJECTS_ROOT).mkdir(parents=True, exist_ok=True)
        p_dirs = sorted((p for p in Path(PROJECTS_ROOT).iterdir() if p.is_dir()),
                        key=lambda p: p.stat().st_mtime, reverse=True)

        def has_images(d: Path) -> bool:
            imgs = d / "images"
            return imgs.is_dir() and any(imgs.iterdir())

        # Prefer a project that actually holds images. Opening a folder can leave
        # an empty project skeleton behind, and picking that one on startup makes
        # the app look like it lost the real dataset.
        p_dirs = [p for p in p_dirs if has_images(p)] +                  [p for p in p_dirs if not has_images(p)]
        for candidate in p_dirs:
            try:
                self.pm = ProjectManager.open(candidate)
                self._on_project_loaded()
                return
            except Exception:
                continue
        try:
            self.pm = ProjectManager.create(Path(PROJECTS_ROOT), "Default_Project")
            self._on_project_loaded()
        except Exception as e:
            QMessageBox.warning(self, "No project",
                                f"Could not create a default project: {e}")

    def _new_project(self):
        dlg = NewProjectDialog(PROJECTS_ROOT, self)
        if dlg.exec():
            try:
                self.pm = ProjectManager.create(Path(dlg.project_root), dlg.project_name)
            except FileExistsError:
                QMessageBox.warning(self, "Name already used",
                                    "A project with that name already exists there.")
                return
            self._on_project_loaded()

    def _open_project(self):
        path = QFileDialog.getExistingDirectory(
            self, "Open project or dataset folder", PROJECTS_ROOT)
        if not path:
            return
        folder = Path(path)
        adopt = False
        if not (folder / "project.db").exists():
            imgs, lbls = ProjectManager.scan_loose_files(folder)
            if imgs or lbls:
                answer = QMessageBox.question(
                    self, "Organise this folder?",
                    f"{folder.name} is not a project yet.\n\n"
                    f"It has {len(imgs)} loose image(s) and {len(lbls)} loose .txt "
                    f"file(s) in its top level.\n\n"
                    "Move them into images/ and labels/ so this folder becomes a "
                    "project?\n\nChoose No to open it as-is and leave every file "
                    "where it is.",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                    QMessageBox.No)
                if answer == QMessageBox.Cancel:
                    return
                adopt = (answer == QMessageBox.Yes)
        try:
            self.pm = ProjectManager.open(folder, adopt_loose_files=adopt)
        except Exception as e:
            QMessageBox.warning(self, "Could not open", str(e))
            return
        self._on_project_loaded()

    def _open_project_path(self, path):
        """Open a project chosen from the Projects grid."""
        from pathlib import Path as _P
        if self.pm:
            self.pm.close()
        try:
            self.pm = ProjectManager.open(_P(path))
        except Exception as e:
            QMessageBox.warning(self, "Could not open", str(e))
            return
        self._on_project_loaded()

    def _on_project_loaded(self):
        added = self.pm.sync_classes_from_labels()
        for view in (self.dataset_view, self.annotate_view, self.versions_view,
                     self.classes_view, self.review_view, self.health_view,
                     self.tools_view):
            view.set_project(self.pm)
        self._refresh_sidebar()
        self.setWindowTitle(f"MyLabeler — {self.pm.root.name}")
        self._on_navigation_changed("dataset")
        if added:
            self.dataset_view.flash(
                f"Registered {len(added)} class id(s) found in label files: "
                + ", ".join(map(str, added)))

    def _on_classes_updated(self):
        if self.pm:
            self.annotate_view.set_project(self.pm)
            self.dataset_view.set_project(self.pm)
            self._refresh_sidebar()

    def _undo_last_delete(self):
        if not self.pm:
            return
        n = self.pm.undo_last_delete()
        if n:
            self._on_dataset_mutated()
            self.dataset_view.refresh()
            self.dataset_view.flash(f"Restored {n} file(s) from the trash.")
        else:
            self.dataset_view.flash("Nothing in the trash to restore.")

    # ----------------------------------------------------------- imports
    def _import_images(self, paths: list):
        if not self.pm:
            QMessageBox.information(self, "No project",
                                    "Open or create a project first.")
            return
        n = self.pm.import_images(paths)
        self._after_import(f"Imported {n} image(s) and their matching annotations.")

    def _import_folder(self, folder_path: str):
        if not self.pm:
            try:
                self.pm = ProjectManager.open(Path(folder_path))
                self._on_project_loaded()
                return
            except Exception as e:
                QMessageBox.warning(self, "Could not open", str(e))
                return
        res = self.pm.import_folder(folder_path)
        self._after_import(
            f"Imported {res['images']} new image(s) from {Path(folder_path).name}.")

    def _after_import(self, message: str):
        self.pm.sync_classes_from_labels()
        self.dataset_view.set_project(self.pm)
        self.annotate_view.set_project(self.pm)
        self._refresh_sidebar()
        self._on_navigation_changed("dataset")
        self.dataset_view.flash(message)

    # ----------------------------------------------------- model & autolabel
    def _load_model(self):
        start_dir = settings().get("model_dir") or str(Path(DEFAULT_MODEL).parent)
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load YOLO model weights", start_dir,
            "PyTorch weights (*.pt);;All files (*.*)")
        if not file_path:
            weights, ok = QInputDialog.getText(
                self, "Load YOLO model", "Model name or full path:",
                text=settings().get("model_weights") or DEFAULT_MODEL)
            if not ok or not weights.strip():
                return
            file_path = weights.strip()

        settings().update(model_weights=file_path,
                          model_dir=str(Path(file_path).parent))
        self.dataset_view.set_model_state("loading", Path(file_path).name)
        self._model_worker = ModelLoadWorker(file_path)
        self._model_worker.finished_ok.connect(self._on_model_loaded)
        self._model_worker.failed.connect(self._on_model_failed)
        self._model_worker.start()

    def _on_model_loaded(self, predictor):
        self.predictor = predictor
        name = Path(predictor.weights).name
        self.dataset_view.set_model_state("ready", name, len(predictor.class_names))
        self.dataset_view.flash(
            f"{name} ready — {len(predictor.class_names)} classes: "
            + ", ".join(list(predictor.class_names)[:5]) + "…")

    def _on_model_failed(self, msg: str):
        self.dataset_view.set_model_state("error", "")
        QMessageBox.critical(self, "Model would not load", msg)

    def _run_autolabel(self, scope: str = "unlabeled", target_files: list = None):
        if not self.pm:
            QMessageBox.information(self, "No project",
                                    "Open or create a project first.")
            return

        if target_files:
            filenames = list(target_files)
        elif scope == "unlabeled":
            filenames = [r["filename"] for r in self.pm.get_images()
                         if r["status"] == "unlabeled"]
        else:
            filenames = [r["filename"] for r in self.pm.get_images()]

        if not filenames:
            self.dataset_view.flash("Every image already has labels — nothing to do.")
            return

        # Try the last-used weights so the class list is populated on open, but
        # never block on it: the dialog can load a model itself.
        if not (self.predictor and self.predictor.is_loaded):
            weights = settings().get("model_weights") or DEFAULT_MODEL
            try:
                self.predictor = YoloPredictor(weights).load()
                self.dataset_view.set_model_state(
                    "ready", Path(weights).name, len(self.predictor.class_names))
            except Exception:
                self.predictor = None

        cfg = settings()
        saved_names = {int(k): v for k, v in (cfg.get("autolabel_names") or {}).items()}
        dlg = AutoLabelDialog(
            self,
            model_name=Path(self.predictor.weights).name if self.predictor else "",
            model_classes=self.predictor.class_names if self.predictor else [],
            project_classes={cid: nm for cid, nm, _ in self.pm.get_classes()},
            confidence=self.dataset_view.confidence(),
            image_count=len(filenames),
            preselected=cfg.get("autolabel_classes") or [],
            preset_names=saved_names,
        )
        dlg.modelChangeRequested.connect(lambda: self._choose_model_for(dlg))
        if not dlg.exec():
            return

        cfg.update(autolabel_classes=dlg.selected_ids,
                   autolabel_names={str(k): v for k, v in dlg.class_names.items()},
                   confidence=round(dlg.confidence, 2))

        # Register names up front so boxes carry a real name the moment they
        # land, rather than showing as class<id> until the run finishes.
        for cid, nm in dlg.class_names.items():
            self.pm.ensure_class(cid, nm)
            self.pm.rename_class(cid, nm)

        if dlg.overwrite and scope == "unlabeled":
            filenames = [r["filename"] for r in self.pm.get_images()]

        self._autolabel_worker = AutoLabelWorker(
            self.predictor, self.pm, filenames, dlg.confidence,
            overwrite=dlg.overwrite,
            classes=dlg.selected_ids, class_names=dlg.class_names)
        self._start_progress(f"Auto-labelling {len(filenames)} image(s)…",
                             len(filenames), self._autolabel_worker)
        self._autolabel_worker.finished_ok.connect(self._on_autolabel_done)
        self._autolabel_worker.failed.connect(
            lambda msg: self._on_worker_failed("Auto-label failed", msg))
        self._autolabel_worker.start()

    def _choose_model_for(self, dlg):
        """Load weights from inside the auto-label dialog and list its classes."""
        start_dir = settings().get("model_dir") or str(Path(DEFAULT_MODEL).parent)
        file_path, _ = QFileDialog.getOpenFileName(
            dlg, "Choose YOLO model weights", start_dir,
            "PyTorch weights (*.pt);;All files (*.*)")
        if not file_path:
            return
        settings().update(model_weights=file_path,
                          model_dir=str(Path(file_path).parent))
        dlg.set_loading(Path(file_path).name)

        worker = ModelLoadWorker(file_path)

        def _ok(predictor):
            self.predictor = predictor
            name = Path(predictor.weights).name
            self.dataset_view.set_model_state(
                "ready", name, len(predictor.class_names))
            dlg.set_model(name, predictor.class_names,
                          {cid: nm for cid, nm, _ in self.pm.get_classes()})

        def _fail(msg):
            self.dataset_view.set_model_state("error", "")
            dlg.set_model_failed(msg)

        worker.finished_ok.connect(_ok)
        worker.failed.connect(_fail)
        self._model_worker = worker
        worker.start()

    def _on_autolabel_done(self, count: int, seen_classes: dict):
        self._close_progress()
        added = self.pm.sync_classes_from_labels(names_hint=seen_classes)
        for cid, name in seen_classes.items():
            self.pm.ensure_class(cid, name)
        self.dataset_view.set_project(self.pm)
        self.annotate_view.set_project(self.pm)
        self.classes_view.refresh()
        self._refresh_sidebar()

        msg = f"Auto-labelled {count} image(s)."
        if added:
            msg += (f" {len(added)} new class id(s) registered so the export "
                    f"stays valid — name them on Classes.")
        self.dataset_view.flash(msg)

    # ------------------------------------------------- augmentation & export
    def _open_augmentation_dialog(self):
        if not self.pm:
            return
        dlg = AugmentationDialog(self, image_count=len(self.pm.get_images()))
        if not dlg.exec():
            return
        filenames = [r["filename"] for r in self.pm.get_images()
                     if load_yolo_annotations(self.pm.label_path(r["filename"]))]
        if not filenames:
            QMessageBox.information(self, "Nothing to augment",
                                    "No annotated images found to augment.")
            return
        self._aug_worker = AugmentationWorker(
            self.pm, dlg.result_config, filenames, dlg.result_variants)
        self._start_progress("Generating augmentations…", len(filenames), self._aug_worker)
        self._aug_worker.finished_ok.connect(self._on_aug_done)
        self._aug_worker.failed.connect(
            lambda msg: self._on_worker_failed("Augmentation failed", msg))
        self._aug_worker.start()

    def _on_aug_done(self, created: int):
        self._close_progress()
        self.dataset_view.refresh()
        self.versions_view.refresh()
        QMessageBox.information(
            self, "Augmentation complete",
            f"Created {created} augmented image/label pairs in\n"
            f"{self.pm.aug_images_dir.parent}\n\n"
            "They stay attached to their source image when the dataset is split, "
            "so no augmented copy can leak into validation.")

    def _export_version(self):
        self._open_export_dialog(preprocess=self.versions_view.preprocess_config(),
                                 default_name=self.versions_view.version_name())

    def _open_export_dialog(self, preprocess=None, default_name: str = ""):
        if not self.pm:
            return
        dlg = ExportDialog(self, default_name=default_name,
                           existing=self._existing_exports(),
                           preprocess_summary=(preprocess.describe() if preprocess else []))
        if not dlg.exec():
            return
        self._export_worker = ExportWorker(
            self.pm, dlg.export_name, dlg.val_percent / 100.0, dlg.include_augmented,
            preprocess=preprocess)
        self._start_progress("Building dataset export…", 100, self._export_worker)
        self._export_worker.finished_ok.connect(self._on_export_done)
        self._export_worker.failed.connect(
            lambda msg: self._on_worker_failed("Export failed", msg))
        self._export_worker.start()

    def _existing_exports(self):
        if not self.pm or not self.pm.exports_dir.exists():
            return []
        return [p.name for p in self.pm.exports_dir.iterdir() if p.is_dir()]

    def _on_export_done(self, report):
        self._close_progress()
        self.versions_view.refresh()
        self._refresh_sidebar()
        self.tools_view.set_upload_folder(str(report.out_root))
        msg = (f"Dataset written to:\n{report.out_root}\n\n"
               f"train: {report.train:,} images    val: {report.val:,} images\n"
               f"classes in data.yaml: {report.classes}\n\n"
               f"Train with:\nyolo detect train data={report.out_root}\\data.yaml "
               f"model=yolo11l.pt")
        if report.warnings:
            msg += "\n\nNotes:\n" + "\n".join(f"• {w}" for w in report.warnings)
        QMessageBox.information(self, "Export complete", msg)

    # ------------------------------------------------------------- progress
    def _start_progress(self, text: str, maximum: int, worker):
        self._close_progress()
        self._progress = QProgressDialog(text, "Cancel", 0, maximum, self)
        self._progress.setWindowModality(Qt.WindowModal)
        self._progress.setMinimumDuration(300)
        self._progress.setAutoClose(False)
        self._progress.setAutoReset(False)
        self._progress.setValue(0)
        self._progress.canceled.connect(worker.cancel)
        worker.progress.connect(self._on_progress_tick)

    def _on_progress_tick(self, done: int, total: int):
        if self._progress:
            self._progress.setMaximum(max(1, total))
            self._progress.setValue(done)

    def _close_progress(self):
        if self._progress is not None:
            self._progress.close()
            self._progress = None

    def _on_worker_failed(self, title: str, msg: str):
        self._close_progress()
        QMessageBox.critical(self, title, msg)

    def closeEvent(self, event):
        for w in (self._model_worker, self._autolabel_worker, self._aug_worker,
                  self._export_worker):
            if w is not None and w.isRunning():
                w.cancel()
                w.wait(2000)
        if self.pm:
            self.pm.close()
        super().closeEvent(event)
