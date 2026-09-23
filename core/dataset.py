"""
core/dataset.py
Turns a labeled project into a ready-to-train YOLO dataset:

    exports/<export_name>/
        train/images  train/labels
        val/images    val/labels
        data.yaml

The split is computed over ORIGINAL images only; each image's augmented
variants follow it into whichever split it landed in. Splitting augmentations
independently would put near-duplicates of the same photo on both sides and
make the validation score meaningless.

Also drives batch augmentation generation and the optional preprocessing steps
configured on the Versions page.
"""
from __future__ import annotations
import random
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import cv2

from core.project import ProjectManager
from core.annotation import BBox, read_label_file, load_yolo_annotations, save_yolo_annotations
from core.augmentation import Augmentor, AugConfig

AUG_SUFFIX_RE = re.compile(r"_aug\d+$")
Progress = Optional[Callable[[int, int], None]]


def source_stem(stem: str) -> str:
    """`frame_07_aug2` -> `frame_07`, so a variant can be traced to its origin."""
    return AUG_SUFFIX_RE.sub("", stem)


def run_batch_augmentation(pm: ProjectManager, config: AugConfig, filenames: List[str],
                           n_variants: int, progress_cb: Progress = None) -> int:
    """
    For each source image (must already have a label file), generate n_variants
    augmented copies and save them into <project>/augmented/{images,labels}.
    Returns number of augmented images created.
    """
    augmentor = Augmentor(config)
    created = 0
    for i, filename in enumerate(filenames):
        label_path = pm.label_path(filename)
        boxes = load_yolo_annotations(label_path)
        if not boxes:
            continue  # nothing to augment without ground truth
        img_path = pm.image_path(filename)
        try:
            variants = augmentor.generate(img_path, boxes, n_variants)
        except (OSError, ValueError):
            if progress_cb:
                progress_cb(i + 1, len(filenames))
            continue
        stem = Path(filename).stem
        ext = Path(filename).suffix
        for v_idx, (aug_img, aug_boxes) in enumerate(variants):
            out_name = f"{stem}_aug{v_idx}{ext}"
            out_img_path = pm.aug_images_dir / out_name
            out_lbl_path = pm.aug_labels_dir / (stem + f"_aug{v_idx}.txt")
            bgr = cv2.cvtColor(aug_img, cv2.COLOR_RGB2BGR)
            out_img_path.parent.mkdir(parents=True, exist_ok=True)
            ok, buf = cv2.imencode(ext if ext else ".jpg", bgr)
            if not ok:
                continue
            buf.tofile(str(out_img_path))       # unicode-safe, unlike cv2.imwrite
            save_yolo_annotations(out_lbl_path, aug_boxes)
            created += 1
        if progress_cb:
            progress_cb(i + 1, len(filenames))
    return created


# ═══════════════════════════════════════════════════════════ preprocessing ══

@dataclass
class PreprocessConfig:
    """The steps configured on the Versions page, applied at export time."""
    filter_null: bool = False           # drop images with no boxes
    random_sample_percent: int = 100    # keep only N% of images
    grayscale: bool = False
    auto_contrast: bool = False
    modify_classes: Dict[int, int] = field(default_factory=dict)   # remap at export
    drop_classes: List[int] = field(default_factory=list)
    resize: Optional[Tuple[int, int]] = None   # (w, h), letterboxed
    seed: int = 42

    @property
    def touches_pixels(self) -> bool:
        return bool(self.grayscale or self.auto_contrast or self.resize)

    @property
    def is_noop(self) -> bool:
        return not (self.filter_null or self.random_sample_percent < 100
                    or self.modify_classes or self.drop_classes
                    or self.touches_pixels)

    def describe(self) -> List[str]:
        out = []
        if self.resize:
            out.append(f"Resize to {self.resize[0]}x{self.resize[1]} (letterboxed)")
        if self.grayscale:
            out.append("Grayscale")
        if self.auto_contrast:
            out.append("Auto-adjust contrast (CLAHE)")
        if self.filter_null:
            out.append("Filter null (drop unannotated images)")
        if self.random_sample_percent < 100:
            out.append(f"Random sample {self.random_sample_percent}%")
        if self.modify_classes:
            pairs = ", ".join(f"{k}->{v}" for k, v in sorted(self.modify_classes.items()))
            out.append(f"Remap classes ({pairs})")
        if self.drop_classes:
            out.append(f"Drop classes {sorted(self.drop_classes)}")
        return out


def _apply_label_steps(boxes: List[BBox], cfg: PreprocessConfig) -> List[BBox]:
    out = []
    for b in boxes:
        if b.class_id in cfg.drop_classes:
            continue
        if b.class_id in cfg.modify_classes:
            b = b.clone()
            b.class_id = cfg.modify_classes[b.class_id]
        out.append(b)
    return out


def _letterbox(img, target_w: int, target_h: int):
    """Resize keeping aspect ratio, padding with grey. Returns (img, scale, pad)."""
    import numpy as np
    h, w = img.shape[:2]
    scale = min(target_w / w, target_h / h)
    new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    canvas = np.full((target_h, target_w, 3), 114, dtype=img.dtype)
    dx, dy = (target_w - new_w) // 2, (target_h - new_h) // 2
    canvas[dy:dy + new_h, dx:dx + new_w] = resized
    return canvas, scale, (dx, dy)


def _remap_for_letterbox(boxes: List[BBox], src_w: int, src_h: int,
                         target_w: int, target_h: int, scale: float,
                         pad: Tuple[int, int]) -> List[BBox]:
    dx, dy = pad
    out = []
    for b in boxes:
        if b.is_polygon:
            pts = []
            for i in range(0, len(b.polygon) - 1, 2):
                px = (b.polygon[i] * src_w * scale + dx) / target_w
                py = (b.polygon[i + 1] * src_h * scale + dy) / target_h
                pts.extend([px, py])
            out.append(BBox.from_polygon(b.class_id, pts, b.confidence))
        else:
            cx = (b.x_center * src_w * scale + dx) / target_w
            cy = (b.y_center * src_h * scale + dy) / target_h
            w = b.width * src_w * scale / target_w
            h = b.height * src_h * scale / target_h
            out.append(BBox(b.class_id, cx, cy, w, h, b.confidence))
    return out


def _process_image(src: Path, dest: Path, boxes: List[BBox],
                   cfg: PreprocessConfig) -> List[BBox]:
    """Write the image (transformed if needed) and return possibly-updated boxes."""
    if not cfg.touches_pixels:
        shutil.copy2(src, dest)
        return boxes

    import numpy as np
    data = np.fromfile(str(src), dtype=np.uint8)      # unicode-safe read
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        shutil.copy2(src, dest)
        return boxes

    src_h, src_w = img.shape[:2]
    if cfg.auto_contrast:
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b_ch = cv2.split(lab)
        l = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
        img = cv2.cvtColor(cv2.merge((l, a, b_ch)), cv2.COLOR_LAB2BGR)
    if cfg.grayscale:
        img = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    if cfg.resize:
        tw, th = cfg.resize
        img, scale, pad = _letterbox(img, tw, th)
        boxes = _remap_for_letterbox(boxes, src_w, src_h, tw, th, scale, pad)

    ok, buf = cv2.imencode(dest.suffix or ".jpg", img)
    if ok:
        buf.tofile(str(dest))
    else:
        shutil.copy2(src, dest)
    return boxes


# ════════════════════════════════════════════════════════════════ exporting ══

@dataclass
class ExportReport:
    out_root: Path
    train: int = 0
    val: int = 0
    test: int = 0
    classes: int = 0
    warnings: List[str] = field(default_factory=list)


def export_dataset(pm: ProjectManager, export_name: str, val_ratio: float = 0.2,
                   include_augmented: bool = True, seed: int = 42,
                   preprocess: Optional[PreprocessConfig] = None,
                   progress_cb: Progress = None) -> ExportReport:
    """Build a train/val split physically on disk under exports/<export_name>/."""
    cfg = preprocess or PreprocessConfig(seed=seed)
    out_root = pm.exports_dir / export_name
    if out_root.exists():
        shutil.rmtree(out_root)
    for split in ("train", "val"):
        (out_root / split / "images").mkdir(parents=True, exist_ok=True)
        (out_root / split / "labels").mkdir(parents=True, exist_ok=True)

    report = ExportReport(out_root=out_root)

    # 1. originals that carry at least one usable box
    originals: List[Tuple[Path, Path]] = []
    for row in pm.get_images():
        lbl = pm.label_path(row["filename"])
        boxes = read_label_file(lbl).boxes if lbl.exists() else []
        if cfg.filter_null and not boxes:
            continue
        if boxes or not cfg.filter_null:
            if lbl.exists() and boxes:
                originals.append((pm.image_path(row["filename"]), lbl))

    if not originals:
        report.warnings.append("No annotated images found - the export is empty.")

    # filename -> stored split, when the project records one
    split_of: Dict[str, str] = {}
    try:
        for row in pm.get_images():
            keys = row.keys() if hasattr(row, "keys") else []
            if "split" in keys and row["split"]:
                split_of[row["filename"]] = row["split"]
    except Exception:
        split_of = {}

    # 2. optional random subsample, applied before splitting
    rng = random.Random(cfg.seed)
    if cfg.random_sample_percent < 100 and originals:
        keep = max(1, round(len(originals) * cfg.random_sample_percent / 100))
        originals = rng.sample(originals, keep)

    # 3. split the ORIGINALS, then attach each one's augmented variants.
    #    An explicit per-image split (set on the Dataset page) always wins;
    #    only images left unassigned get dealt out by val_ratio.
    assigned_train, assigned_val, assigned_test, unassigned = [], [], [], []
    for img_path, lbl in originals:
        split = split_of.get(img_path.name, "")
        if split == "train":
            assigned_train.append((img_path, lbl))
        elif split in ("valid", "val"):
            assigned_val.append((img_path, lbl))
        elif split == "test":
            assigned_test.append((img_path, lbl))
        else:
            unassigned.append((img_path, lbl))

    rng.shuffle(unassigned)
    n_val = int(len(unassigned) * val_ratio)
    if unassigned and not assigned_val and n_val == 0:
        n_val = 1          # never produce an empty validation set by rounding
    val_originals = assigned_val + unassigned[:n_val]
    train_originals = assigned_train + unassigned[n_val:]
    test_originals = assigned_test
    if split_of:
        n_assigned = len(assigned_train) + len(assigned_val) + len(assigned_test)
        report.warnings.append(
            f"{n_assigned:,} image(s) used their assigned split; "
            f"{len(unassigned):,} unassigned image(s) were dealt out at "
            f"{int(val_ratio * 100)}% validation.")

    # A test folder is only written when something is actually assigned to it,
    # so two-way exports keep the shape they always had.
    if test_originals:
        for sub in ("images", "labels"):
            (out_root / "test" / sub).mkdir(parents=True, exist_ok=True)

    aug_by_source: Dict[str, List[Tuple[Path, Path]]] = {}
    if include_augmented and pm.aug_images_dir.exists():
        for img_path in sorted(pm.aug_images_dir.glob("*")):
            lbl_path = pm.aug_labels_dir / (img_path.stem + ".txt")
            if lbl_path.exists() and lbl_path.stat().st_size > 0:
                aug_by_source.setdefault(source_stem(img_path.stem), []).append(
                    (img_path, lbl_path))

    def with_augs(pairs):
        out = list(pairs)
        for img_path, _ in pairs:
            out.extend(aug_by_source.get(img_path.stem, []))
        return out

    train_pairs = with_augs(train_originals)
    val_pairs = with_augs(val_originals)
    test_pairs = with_augs(test_originals)

    orphan_augs = sum(len(v) for k, v in aug_by_source.items()
                      if k not in {p[0].stem for p in originals})
    if orphan_augs:
        report.warnings.append(
            f"{orphan_augs} augmented image(s) had no surviving source image and were skipped.")

    # 4. copy, applying pixel/label preprocessing
    total = len(train_pairs) + len(val_pairs) + len(test_pairs) or 1
    done = 0
    used_class_ids = set()

    def _copy_split(pairs, split):
        nonlocal done
        for img_path, lbl_path in pairs:
            boxes = _apply_label_steps(read_label_file(lbl_path).boxes, cfg)
            if cfg.filter_null and not boxes:
                done += 1
                continue
            dest_img = out_root / split / "images" / img_path.name
            boxes = _process_image(img_path, dest_img, boxes, cfg)
            save_yolo_annotations(
                out_root / split / "labels" / (img_path.stem + ".txt"), boxes)
            used_class_ids.update(b.class_id for b in boxes)
            done += 1
            if progress_cb:
                progress_cb(done, total)

    _copy_split(train_pairs, "train")
    _copy_split(val_pairs, "val")
    if test_pairs:
        _copy_split(test_pairs, "test")

    report.train = len(list((out_root / "train" / "images").iterdir()))
    report.val = len(list((out_root / "val" / "images").iterdir()))
    if test_pairs:
        report.test = len(list((out_root / "test" / "images").iterdir()))

    # 5. data.yaml - names must cover every class id that appears in the labels,
    #    otherwise Ultralytics rejects the dataset at training time.
    known = {cid: name for cid, name, _ in pm.get_classes()}
    max_id = max(list(known.keys()) + list(used_class_ids), default=-1)
    names = []
    unnamed = []
    for i in range(max_id + 1):
        if i in known:
            names.append(known[i])
        elif i in used_class_ids:
            names.append(f"class{i}")
            unnamed.append(i)
        else:
            names.append("unused")
    if unnamed:
        report.warnings.append(
            "Label files use class id(s) " + ", ".join(map(str, unnamed))
            + " that are not named in the project. They were exported as "
              "class<id> - name them on the Classes page for a cleaner data.yaml.")
    report.classes = max_id + 1

    yaml_lines = [
        f"path: {out_root.resolve()}",
        "train: train/images",
        "val: val/images",
    ]
    if test_pairs:
        yaml_lines.append("test: test/images")
    yaml_lines.append("names:")
    yaml_lines += [f"  {i}: {n}" for i, n in enumerate(names)]
    if cfg.describe():
        yaml_lines.append("")
        yaml_lines += [f"# preprocessing: {s}" for s in cfg.describe()]
    (out_root / "data.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")

    return report
