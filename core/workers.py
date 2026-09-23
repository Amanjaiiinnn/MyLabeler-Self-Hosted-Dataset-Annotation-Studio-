"""core/workers.py - QThread workers for long-running tasks.

Every worker is cancellable (call .cancel()) and reports progress, so the
progress dialogs in the UI are not decorative.
"""
from __future__ import annotations
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QThread, Signal

from core.yolo_predictor import YoloPredictor
from core.project import ProjectManager
from core.annotation import save_yolo_annotations
from core.augmentation import AugConfig
from core.dataset import run_batch_augmentation, export_dataset, PreprocessConfig


class CancellableWorker(QThread):
    """Shared cancel flag + a uniform failed/progress contract."""
    progress = Signal(int, int)     # done, total
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled


class ModelLoadWorker(CancellableWorker):
    finished_ok = Signal(object)   # YoloPredictor

    def __init__(self, weights: str):
        super().__init__()
        self.weights = weights

    def run(self):
        try:
            predictor = YoloPredictor(self.weights).load()
            self.finished_ok.emit(predictor)
        except Exception as e:
            self.failed.emit(str(e))


class AutoLabelWorker(CancellableWorker):
    finished_ok = Signal(int, dict)   # count labeled, {class_id: name} seen

    def __init__(self, predictor: YoloPredictor, pm: ProjectManager,
                 filenames: List[str], conf: float, overwrite: bool,
                 classes: Optional[List[int]] = None,
                 class_names: Optional[Dict[int, str]] = None):
        super().__init__()
        self.predictor = predictor
        self.pm = pm
        self.filenames = filenames
        self.conf = conf
        self.overwrite = overwrite
        # Restrict detection to these model class ids (None = every class),
        # and use the names the user typed rather than the model's own.
        self.classes = list(classes) if classes else None
        self.class_names = dict(class_names or {})

    def run(self):
        try:
            count = 0
            seen: Dict[int, str] = {}
            model_names = list(getattr(self.predictor, "class_names", []) or [])
            for i, filename in enumerate(self.filenames):
                if self.cancelled:
                    break
                label_path = self.pm.label_path(filename)
                if label_path.exists() and label_path.stat().st_size > 0 and not self.overwrite:
                    self.progress.emit(i + 1, len(self.filenames))
                    continue
                img_path = self.pm.image_path(filename)
                boxes = self.predictor.predict(img_path, conf=self.conf,
                                               classes=self.classes)
                save_yolo_annotations(label_path, boxes)
                self.pm.set_status(filename, "auto-labeled" if boxes else "unlabeled")
                for b in boxes:
                    if b.class_id not in seen:
                        seen[b.class_id] = self.class_names.get(
                            b.class_id,
                            model_names[b.class_id]
                            if b.class_id < len(model_names)
                            else f"class{b.class_id}")
                count += 1
                self.progress.emit(i + 1, len(self.filenames))
            self.finished_ok.emit(count, seen)
        except Exception as e:
            self.failed.emit(str(e))


class AugmentationWorker(CancellableWorker):
    finished_ok = Signal(int)

    def __init__(self, pm: ProjectManager, config: AugConfig, filenames: List[str],
                 n_variants: int):
        super().__init__()
        self.pm = pm
        self.config = config
        self.filenames = filenames
        self.n_variants = n_variants

    def run(self):
        try:
            def cb(done, total):
                self.progress.emit(done, total)
            created = run_batch_augmentation(
                self.pm, self.config, self.filenames, self.n_variants, progress_cb=cb)
            self.finished_ok.emit(created)
        except Exception as e:
            self.failed.emit(str(e))


class ExportWorker(CancellableWorker):
    finished_ok = Signal(object)   # ExportReport

    def __init__(self, pm: ProjectManager, export_name: str, val_ratio: float,
                 include_augmented: bool,
                 preprocess: Optional[PreprocessConfig] = None):
        super().__init__()
        self.pm = pm
        self.export_name = export_name
        self.val_ratio = val_ratio
        self.include_augmented = include_augmented
        self.preprocess = preprocess

    def run(self):
        try:
            report = export_dataset(
                self.pm, self.export_name, self.val_ratio, self.include_augmented,
                preprocess=self.preprocess,
                progress_cb=lambda d, t: self.progress.emit(d, t))
            self.finished_ok.emit(report)
        except Exception as e:
            self.failed.emit(str(e))


class FunctionWorker(CancellableWorker):
    """
    Runs any callable off the GUI thread. Used by the audit, class-remap and
    subset tools so a 30k-image scan does not freeze the window.

    The callable receives a `progress` keyword taking (done, total).
    """
    finished_ok = Signal(object)

    def __init__(self, fn: Callable, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            def cb(done, total):
                self.progress.emit(done, total)
            result = self._fn(*self._args, progress=cb, **self._kwargs)
            self.finished_ok.emit(result)
        except Exception as e:
            self.failed.emit(str(e))
