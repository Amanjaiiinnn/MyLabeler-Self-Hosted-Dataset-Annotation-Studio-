"""
core/yolo_predictor.py
Thin wrapper around Ultralytics YOLO for auto-labeling assistance.

Works with any Ultralytics-compatible weights: 'yolo26l.pt' (COCO-pretrained,
auto-downloads on first use), 'yolo26n.pt', or your own trained
'runs/detect/train/weights/best.pt'.
"""
from __future__ import annotations
from pathlib import Path
from typing import List, Optional

from core.annotation import BBox

DEFAULT_MODEL = r"C:\Users\india\Desktop\Inspect Model __ camera\Yolo Models\yolo11l_saved_model\yolo11l.pt"


class YoloPredictor:
    def __init__(self, weights: str = DEFAULT_MODEL):
        self.weights = weights
        self._model = None
        self.class_names: List[str] = []

    def load(self):
        from ultralytics import YOLO  # imported lazily so the GUI starts fast
        self._model = YOLO(self.weights)
        self.class_names = list(self._model.names.values())
        return self

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def predict(self, image_path: Path, conf: float = 0.25, iou: float = 0.45,
                imgsz: int = 640, classes: Optional[List[int]] = None) -> List[BBox]:
        """
        Run inference on one image, return BBoxes in YOLO-normalized format
        with class_id matching THIS MODEL's class indices (see class_names).
        """
        if not self.is_loaded:
            self.load()
        results = self._model.predict(
            source=str(image_path), conf=conf, iou=iou, imgsz=imgsz,
            classes=classes, verbose=False,
        )
        boxes_out: List[BBox] = []
        if not results:
            return boxes_out
        r = results[0]
        img_h, img_w = r.orig_shape
        for box in r.boxes:
            cid = int(box.cls.item())
            confv = float(box.conf.item())
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
            boxes_out.append(BBox.from_pixels(cid, x1, y1, x2, y2, img_w, img_h, confidence=confv))
        return boxes_out
