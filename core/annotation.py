"""
core/annotation.py
Annotation data model and YOLO-format (.txt) read/write helpers.

Two line formats are supported, auto-detected on read:

    axis-aligned box   class_id xc yc w h                       (5 tokens)
    OBB / polygon      class_id x1 y1 x2 y2 x3 y3 x4 y4 ...     (odd, >= 9 tokens)

Every value is normalized 0-1. A polygon annotation also carries the
axis-aligned bounds of its points so the rest of the app (canvas, thumbnails,
augmentation) can treat it like a box; the original points are preserved and
re-written verbatim unless the shape is actually edited.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


@dataclass
class BBox:
    class_id: int
    x_center: float   # normalized 0-1
    y_center: float   # normalized 0-1
    width: float      # normalized 0-1
    height: float     # normalized 0-1
    confidence: Optional[float] = None   # set by a model, None when human-drawn
    polygon: Optional[List[float]] = None  # normalized [x1,y1,x2,y2,...] for OBB/segmentation

    # ---------- shape kind ----------
    @property
    def is_polygon(self) -> bool:
        return bool(self.polygon) and len(self.polygon) >= 8

    # ---------- conversions ----------
    def to_pixels(self, img_w: int, img_h: int) -> Tuple[float, float, float, float]:
        """Return (x1, y1, x2, y2) of the axis-aligned bounds in pixel coordinates."""
        cx, cy = self.x_center * img_w, self.y_center * img_h
        w, h = self.width * img_w, self.height * img_h
        return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2

    def polygon_pixels(self, img_w: int, img_h: int) -> List[Tuple[float, float]]:
        """Return the polygon points in pixel coordinates (empty if not a polygon)."""
        if not self.is_polygon:
            return []
        pts = self.polygon
        return [(pts[i] * img_w, pts[i + 1] * img_h) for i in range(0, len(pts) - 1, 2)]

    @classmethod
    def from_pixels(cls, class_id: int, x1: float, y1: float, x2: float, y2: float,
                    img_w: int, img_h: int, confidence: Optional[float] = None,
                    polygon: Optional[List[float]] = None) -> "BBox":
        if not img_w or not img_h:
            raise ValueError("image dimensions must be non-zero to normalize a box")
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        x1, y1 = max(0.0, x1), max(0.0, y1)
        x2, y2 = min(float(img_w), x2), min(float(img_h), y2)
        w, h = x2 - x1, y2 - y1
        cx, cy = x1 + w / 2, y1 + h / 2
        return cls(
            class_id=class_id,
            x_center=cx / img_w,
            y_center=cy / img_h,
            width=w / img_w,
            height=h / img_h,
            confidence=confidence,
            polygon=polygon,
        )

    @classmethod
    def from_polygon(cls, class_id: int, points_norm: Sequence[float],
                     confidence: Optional[float] = None) -> "BBox":
        """Build from a flat sequence of normalized [x1,y1,x2,y2,...] points."""
        pts = [float(v) for v in points_norm]
        xs, ys = pts[0::2], pts[1::2]
        x1, x2 = min(xs), max(xs)
        y1, y2 = min(ys), max(ys)
        return cls(
            class_id=class_id,
            x_center=(x1 + x2) / 2,
            y_center=(y1 + y2) / 2,
            width=x2 - x1,
            height=y2 - y1,
            confidence=confidence,
            polygon=pts,
        )

    # ---------- serialization ----------
    def to_yolo_line(self) -> str:
        if self.is_polygon:
            coords = " ".join(f"{v:.6f}" for v in self.polygon)
            return f"{self.class_id} {coords}"
        return (f"{self.class_id} {self.x_center:.6f} {self.y_center:.6f} "
                f"{self.width:.6f} {self.height:.6f}")

    @classmethod
    def from_yolo_line(cls, line: str) -> Optional["BBox"]:
        """Parse one label line. Returns None for blank or malformed lines."""
        parts = line.strip().split()
        if len(parts) < 5:
            return None
        try:
            cid = int(float(parts[0]))       # tolerate "0" and "0.0"
            nums = [float(v) for v in parts[1:]]
        except (TypeError, ValueError):
            return None
        if any(v != v for v in nums):        # NaN check
            return None

        if len(nums) == 4:
            return cls(cid, nums[0], nums[1], nums[2], nums[3])
        if len(nums) >= 8 and len(nums) % 2 == 0:
            return cls.from_polygon(cid, nums)
        return None

    def is_valid(self) -> bool:
        if self.is_polygon:
            return len(self.polygon) >= 8
        return self.width > 1e-4 and self.height > 1e-4

    def clone(self) -> "BBox":
        return BBox(self.class_id, self.x_center, self.y_center, self.width,
                    self.height, self.confidence,
                    list(self.polygon) if self.polygon else None)

    def transformed_to_bounds(self, x1: float, y1: float, x2: float, y2: float) -> "BBox":
        """
        Return a copy whose axis-aligned bounds are (x1,y1)-(x2,y2) in normalized
        coords. A polygon is affinely mapped from its old bounds onto the new ones,
        so dragging or resizing an OBB keeps its rotation.
        """
        nx1, nx2 = sorted((x1, x2))
        ny1, ny2 = sorted((y1, y2))
        new = BBox(
            class_id=self.class_id,
            x_center=(nx1 + nx2) / 2, y_center=(ny1 + ny2) / 2,
            width=nx2 - nx1, height=ny2 - ny1,
            confidence=self.confidence,
        )
        if self.is_polygon:
            ox1 = self.x_center - self.width / 2
            oy1 = self.y_center - self.height / 2
            sx = (nx2 - nx1) / self.width if self.width > 1e-9 else 1.0
            sy = (ny2 - ny1) / self.height if self.height > 1e-9 else 1.0
            pts = []
            for i in range(0, len(self.polygon) - 1, 2):
                pts.append(nx1 + (self.polygon[i] - ox1) * sx)
                pts.append(ny1 + (self.polygon[i + 1] - oy1) * sy)
            new.polygon = pts
        return new


@dataclass
class LabelFile:
    """A parsed label file, keeping track of lines that could not be understood."""
    boxes: List[BBox] = field(default_factory=list)
    malformed: List[str] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return not self.boxes and not self.malformed


def read_label_file(txt_path: Path) -> LabelFile:
    """Parse a label file without ever raising. Bad lines land in .malformed."""
    out = LabelFile()
    if not txt_path.exists():
        return out
    try:
        text = txt_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        out.error = str(e)
        return out
    for line in text.splitlines():
        if not line.strip():
            continue
        b = BBox.from_yolo_line(line)
        if b is None:
            out.malformed.append(line.strip())
        else:
            out.boxes.append(b)
    return out


def load_yolo_annotations(txt_path: Path) -> List[BBox]:
    """Boxes only. Malformed lines are skipped rather than raising."""
    return read_label_file(txt_path).boxes


def save_yolo_annotations(txt_path: Path, boxes: List[BBox]) -> None:
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [b.to_yolo_line() for b in boxes if b.is_valid()]
    txt_path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")
