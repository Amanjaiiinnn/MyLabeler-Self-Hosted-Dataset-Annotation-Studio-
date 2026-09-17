"""
core/augmentation.py
Roboflow-style augmentation engine built on Albumentations.

Axis-aligned boxes ride along as YOLO bboxes. OBB / polygon annotations are
carried as keypoints so that flips, rotations and shears move their corners
correctly instead of collapsing them to an upright rectangle.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np
import albumentations as A

from core.annotation import BBox


@dataclass
class AugConfig:
    """Toggle + strength for each augmentation. Mirrors a Roboflow 'Generate' page."""
    flip_horizontal: bool = True
    flip_vertical: bool = False

    rotate: bool = False
    rotate_degrees: int = 15               # +/- range

    crop: bool = False
    crop_percent: int = 10                 # up to N% cropped off each side

    brightness_contrast: bool = True
    brightness_limit: float = 0.2
    contrast_limit: float = 0.2

    hue_saturation: bool = False
    hue_shift: int = 10
    sat_shift: int = 15

    blur: bool = False
    blur_limit: int = 3

    noise: bool = False
    noise_strength: float = 0.02           # fraction of 255

    cutout: bool = False                   # random erasing / coarse dropout
    cutout_count: int = 3
    cutout_size_percent: int = 10          # hole size as % of image dim

    grayscale: bool = False
    grayscale_prob: float = 0.1

    shear: bool = False
    shear_degrees: int = 10

    def build_pipeline(self) -> A.Compose:
        tfs = []
        if self.flip_horizontal:
            tfs.append(A.HorizontalFlip(p=0.5))
        if self.flip_vertical:
            tfs.append(A.VerticalFlip(p=0.5))
        if self.rotate:
            tfs.append(A.Rotate(limit=self.rotate_degrees, p=0.6,
                                border_mode=cv2.BORDER_CONSTANT))
        if self.shear:
            tfs.append(A.Affine(shear=(-self.shear_degrees, self.shear_degrees), p=0.5))
        if self.crop:
            # Crop up to N% off each border, keeping the original aspect ratio.
            # (The old RandomSizedBBoxSafeCrop forced every output to 640x640,
            #  which silently distorted every non-square image.)
            frac = max(0.0, min(0.4, self.crop_percent / 100.0))
            tfs.append(A.RandomCropFromBorders(
                crop_left=frac, crop_right=frac, crop_top=frac, crop_bottom=frac, p=0.5))
        if self.brightness_contrast:
            tfs.append(A.RandomBrightnessContrast(
                brightness_limit=self.brightness_limit,
                contrast_limit=self.contrast_limit, p=0.7))
        if self.hue_saturation:
            tfs.append(A.HueSaturationValue(
                hue_shift_limit=self.hue_shift, sat_shift_limit=self.sat_shift,
                val_shift_limit=0, p=0.6))
        if self.blur:
            k = max(3, self.blur_limit | 1)  # must be odd
            tfs.append(A.Blur(blur_limit=(3, k), p=0.4))
        if self.noise:
            tfs.append(A.GaussNoise(std_range=(0.0, max(0.01, self.noise_strength)), p=0.4))
        if self.cutout:
            hole_frac = max(0.04, self.cutout_size_percent / 100.0)
            tfs.append(A.CoarseDropout(
                num_holes_range=(1, max(1, self.cutout_count)),
                hole_height_range=(hole_frac, hole_frac),
                hole_width_range=(hole_frac, hole_frac),
                p=0.5))
        if self.grayscale:
            tfs.append(A.ToGray(p=self.grayscale_prob))

        return A.Compose(
            tfs,
            bbox_params=A.BboxParams(format="yolo", label_fields=["class_labels"],
                                     min_visibility=0.2, filter_invalid_bboxes=True),
            keypoint_params=A.KeypointParams(format="xy", label_fields=["kp_labels"],
                                             remove_invisible=False),
        )


class Augmentor:
    def __init__(self, config: AugConfig):
        self.config = config
        self.pipeline = config.build_pipeline()

    def augment_once(self, image: np.ndarray,
                     boxes: List[BBox]) -> Tuple[np.ndarray, List[BBox]]:
        """Apply one random augmentation draw to an image and its annotations."""
        h, w = image.shape[:2]

        rect_boxes = [b for b in boxes if not b.is_polygon]
        poly_boxes = [b for b in boxes if b.is_polygon]

        yolo_boxes = [[b.x_center, b.y_center, b.width, b.height] for b in rect_boxes]
        labels = [b.class_id for b in rect_boxes]

        # every polygon vertex becomes a keypoint tagged with its polygon index
        keypoints, kp_labels = [], []
        for idx, b in enumerate(poly_boxes):
            for (px, py) in b.polygon_pixels(w, h):
                keypoints.append((px, py))
                kp_labels.append(idx)

        try:
            result = self.pipeline(image=image, bboxes=yolo_boxes,
                                   class_labels=labels, keypoints=keypoints,
                                   kp_labels=kp_labels)
        except Exception:
            # a pathological draw wiped everything - fall back to the original
            return image, boxes

        out_img = result["image"]
        oh, ow = out_img.shape[:2]
        out_boxes = [
            BBox(class_id=int(cls), x_center=bb[0], y_center=bb[1],
                 width=bb[2], height=bb[3])
            for bb, cls in zip(result["bboxes"], result["class_labels"])
        ]

        # rebuild each polygon from its transformed vertices
        grouped: dict = {}
        for (px, py), idx in zip(result["keypoints"], result["kp_labels"]):
            grouped.setdefault(int(idx), []).append((px, py))
        for idx, pts in grouped.items():
            src = poly_boxes[idx]
            if len(pts) < 4:
                continue
            flat = []
            for (px, py) in pts:
                flat.append(min(1.0, max(0.0, px / ow)))
                flat.append(min(1.0, max(0.0, py / oh)))
            rebuilt = BBox.from_polygon(src.class_id, flat, src.confidence)
            if rebuilt.width > 1e-3 and rebuilt.height > 1e-3:
                out_boxes.append(rebuilt)

        return out_img, out_boxes

    def generate(self, image_path: Path, boxes: List[BBox],
                 n_variants: int) -> List[Tuple[np.ndarray, List[BBox]]]:
        data = np.fromfile(str(image_path), dtype=np.uint8)   # unicode-safe
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            raise OSError(f"Could not read image: {image_path}")
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        outputs = []
        for _ in range(n_variants):
            aug_img, aug_boxes = self.augment_once(img, boxes)
            outputs.append((aug_img, aug_boxes))
        return outputs
