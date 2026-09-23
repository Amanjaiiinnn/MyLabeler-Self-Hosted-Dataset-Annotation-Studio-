"""
core/labelops.py
Dataset audit, class remapping and subset extraction - the batch operations
that used to live in a folder of one-off scripts.

Everything here is a plain function over a DatasetSource so it can run against
the open project or any dataset folder, and everything destructive goes through
core.trash rather than os.remove.
"""
from __future__ import annotations
import math
import random
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from core.annotation import BBox, read_label_file, save_yolo_annotations
from core.dataset_source import DatasetSource, Pair
from core.trash import Trash

Progress = Optional[Callable[[int, int], None]]


def _tick(cb: Progress, done: int, total: int):
    if cb:
        cb(done, total)


# ══════════════════════════════════════════════════════════════════ audit ══

@dataclass
class AuditReport:
    """What is wrong with a dataset, split by problem."""
    total_images: int = 0
    total_labels: int = 0
    total_boxes: int = 0

    images_without_labels: List[Pair] = field(default_factory=list)
    labels_without_images: List[Pair] = field(default_factory=list)
    empty_labels: List[Pair] = field(default_factory=list)
    malformed_labels: List[Tuple[Pair, List[str]]] = field(default_factory=list)
    unreadable_images: List[Pair] = field(default_factory=list)
    out_of_range_boxes: List[Tuple[Pair, int]] = field(default_factory=list)

    class_counts: Dict[int, int] = field(default_factory=dict)
    images_per_class: Dict[int, int] = field(default_factory=dict)
    multiclass_images: List[Pair] = field(default_factory=list)
    polygon_boxes: int = 0
    per_split: Dict[str, int] = field(default_factory=dict)

    @property
    def problem_count(self) -> int:
        return (len(self.images_without_labels) + len(self.labels_without_images)
                + len(self.empty_labels) + len(self.malformed_labels)
                + len(self.unreadable_images) + len(self.out_of_range_boxes))

    def summary_rows(self) -> List[Tuple[str, int, str]]:
        """(problem, count, what fixing it does) - drives the health table."""
        return [
            ("Images with no label file", len(self.images_without_labels),
             "Move the image to .trash"),
            ("Label files with no image", len(self.labels_without_images),
             "Move the label to .trash"),
            ("Empty label files (0 boxes)", len(self.empty_labels),
             "Move image + label to .trash"),
            ("Label files with unparseable lines", len(self.malformed_labels),
             "Rewrite the file, dropping bad lines"),
            ("Boxes with coords outside 0-1", len(self.out_of_range_boxes),
             "Clamp coordinates into range"),
            ("Images that cannot be opened", len(self.unreadable_images),
             "Move image + label to .trash"),
        ]


def audit(source: DatasetSource, splits: Optional[Iterable[str]] = None,
          check_images: bool = False, progress: Progress = None) -> AuditReport:
    """
    Full dataset health scan. `check_images=True` additionally opens every image
    to catch truncated files, which is much slower.
    """
    rep = AuditReport()
    pairs = source.pairs(splits)
    rep.total_images = len(pairs)
    total = len(pairs) or 1

    for i, pair in enumerate(pairs):
        rep.per_split[pair.split] = rep.per_split.get(pair.split, 0) + 1

        if check_images:
            if not _image_ok(pair.image):
                rep.unreadable_images.append(pair)

        if not pair.has_label:
            rep.images_without_labels.append(pair)
            _tick(progress, i + 1, total)
            continue

        rep.total_labels += 1
        lf = read_label_file(pair.label)

        if lf.malformed:
            rep.malformed_labels.append((pair, lf.malformed))
        if not lf.boxes:
            rep.empty_labels.append(pair)
            _tick(progress, i + 1, total)
            continue

        rep.total_boxes += len(lf.boxes)
        seen = set()
        bad_coords = 0
        for b in lf.boxes:
            rep.class_counts[b.class_id] = rep.class_counts.get(b.class_id, 0) + 1
            seen.add(b.class_id)
            if b.is_polygon:
                rep.polygon_boxes += 1
            if _out_of_range(b):
                bad_coords += 1
        if bad_coords:
            rep.out_of_range_boxes.append((pair, bad_coords))
        for cid in seen:
            rep.images_per_class[cid] = rep.images_per_class.get(cid, 0) + 1
        if len(seen) > 1:
            rep.multiclass_images.append(pair)

        _tick(progress, i + 1, total)

    rep.labels_without_images = source.orphan_labels(splits)
    rep.total_labels += len(rep.labels_without_images)
    return rep


def _out_of_range(b: BBox) -> bool:
    vals = b.polygon if b.is_polygon else [
        b.x_center - b.width / 2, b.y_center - b.height / 2,
        b.x_center + b.width / 2, b.y_center + b.height / 2]
    return any(v < -1e-6 or v > 1 + 1e-6 for v in vals)


def _image_ok(path: Optional[Path]) -> bool:
    if path is None or not path.exists():
        return False
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════ fixes ══

@dataclass
class FixResult:
    trashed: int = 0
    rewritten: int = 0
    details: List[str] = field(default_factory=list)


def fix_unpaired(source: DatasetSource, report: AuditReport, trash: Trash,
                 drop_images: bool = True, drop_labels: bool = True,
                 dry_run: bool = True) -> FixResult:
    """Replaces check_images_labels.py and cleanup_unpaired_files.py."""
    res = FixResult()
    victims: List[Path] = []
    if drop_images:
        for p in report.images_without_labels:
            victims.append(p.image)
            res.details.append(f"image with no label: {p.image.name}")
    if drop_labels:
        for p in report.labels_without_images:
            victims.append(p.label)
            res.details.append(f"label with no image: {p.label.name}")
    victims = [v for v in victims if v]
    if dry_run:
        res.trashed = len(victims)
        return res
    res.trashed = trash.send(victims, reason="unpaired files").count
    return res


def fix_empty_labels(source: DatasetSource, report: AuditReport, trash: Trash,
                     dry_run: bool = True) -> FixResult:
    """Replaces find-empty-file.py + review_and_clean.py's delete action."""
    res = FixResult()
    victims: List[Path] = []
    for p in report.empty_labels:
        if p.image:
            victims.append(p.image)
        if p.label:
            victims.append(p.label)
        res.details.append(f"empty label: {p.stem}")
    if dry_run:
        res.trashed = len(victims)
        return res
    res.trashed = trash.send(victims, reason="empty labels").count
    return res


def fix_malformed_labels(source: DatasetSource, report: AuditReport,
                         dry_run: bool = True) -> FixResult:
    """Rewrite label files, keeping only lines we can parse."""
    res = FixResult()
    for pair, bad in report.malformed_labels:
        res.details.append(f"{pair.label.name}: dropping {len(bad)} line(s)")
        if dry_run:
            res.rewritten += 1
            continue
        lf = read_label_file(pair.label)
        save_yolo_annotations(pair.label, lf.boxes)
        res.rewritten += 1
    return res


def fix_out_of_range(source: DatasetSource, report: AuditReport,
                     dry_run: bool = True) -> FixResult:
    """Clamp every coordinate into 0-1 without changing which boxes exist."""
    res = FixResult()
    for pair, count in report.out_of_range_boxes:
        res.details.append(f"{pair.label.name}: clamping {count} box(es)")
        if dry_run:
            res.rewritten += 1
            continue
        lf = read_label_file(pair.label)
        save_yolo_annotations(pair.label, [_clamp(b) for b in lf.boxes])
        res.rewritten += 1
    return res


def _clamp(b: BBox) -> BBox:
    if b.is_polygon:
        out = b.clone()
        out.polygon = [min(1.0, max(0.0, v)) for v in out.polygon]
        return BBox.from_polygon(out.class_id, out.polygon, out.confidence)
    x1 = min(1.0, max(0.0, b.x_center - b.width / 2))
    y1 = min(1.0, max(0.0, b.y_center - b.height / 2))
    x2 = min(1.0, max(0.0, b.x_center + b.width / 2))
    y2 = min(1.0, max(0.0, b.y_center + b.height / 2))
    return BBox(b.class_id, (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1, b.confidence)


def trash_pairs(pairs: Sequence[Pair], trash: Trash, reason: str = "") -> int:
    """Send whole image+label pairs to the trash. Used by review mode."""
    victims: List[Path] = []
    for p in pairs:
        if p.image:
            victims.append(p.image)
        if p.label:
            victims.append(p.label)
    return trash.send(victims, reason=reason).count


# ═══════════════════════════════════════════════════════════ class remaps ══

@dataclass
class RemapResult:
    files_changed: int = 0
    boxes_changed: int = 0
    files_scanned: int = 0


def remap_classes(source: DatasetSource, mapping: Dict[int, int],
                  splits: Optional[Iterable[str]] = None, dry_run: bool = True,
                  progress: Progress = None) -> RemapResult:
    """
    Apply {old_id: new_id} across every label file.

    Covers all three of the old scripts:
        change-class.py   mapping = {every id: target}   (build with merge_all_mapping)
        test.py           mapping = {0: 1, 1: 0}
        one-off fixes     mapping = {5: 2}
    Bounding-box and polygon coordinates are untouched.
    """
    res = RemapResult()
    files = source.label_files(splits)
    total = len(files) or 1

    for i, path in enumerate(files):
        res.files_scanned += 1
        lf = read_label_file(path)
        if not lf.boxes:
            _tick(progress, i + 1, total)
            continue
        changed = 0
        for b in lf.boxes:
            if b.class_id in mapping and mapping[b.class_id] != b.class_id:
                if not dry_run:
                    b.class_id = mapping[b.class_id]
                changed += 1
        if changed:
            res.files_changed += 1
            res.boxes_changed += changed
            if not dry_run:
                save_yolo_annotations(path, lf.boxes)
        _tick(progress, i + 1, total)
    return res


def merge_all_mapping(present_ids: Iterable[int], target: int) -> Dict[int, int]:
    """Everything becomes one class - the change-class.py behaviour."""
    return {cid: target for cid in present_ids}


def swap_mapping(a: int, b: int) -> Dict[int, int]:
    """The test.py behaviour, for any two ids."""
    return {a: b, b: a}


def delete_class(source: DatasetSource, class_id: int,
                 splits: Optional[Iterable[str]] = None, dry_run: bool = True,
                 progress: Progress = None) -> RemapResult:
    """Drop every box of one class, leaving the images in place."""
    res = RemapResult()
    files = source.label_files(splits)
    total = len(files) or 1
    for i, path in enumerate(files):
        res.files_scanned += 1
        lf = read_label_file(path)
        keep = [b for b in lf.boxes if b.class_id != class_id]
        removed = len(lf.boxes) - len(keep)
        if removed:
            res.files_changed += 1
            res.boxes_changed += removed
            if not dry_run:
                save_yolo_annotations(path, keep)
        _tick(progress, i + 1, total)
    return res


def reindex_classes(source: DatasetSource, keep_order: Sequence[int],
                    splits: Optional[Iterable[str]] = None,
                    dry_run: bool = True) -> RemapResult:
    """Renumber classes to 0..n-1 in the given order, closing any gaps."""
    mapping = {old: new for new, old in enumerate(keep_order)}
    return remap_classes(source, mapping, splits, dry_run)


# ═════════════════════════════════════════════════════════════════ subsets ══

@dataclass
class SubsetResult:
    output_dir: Path
    copied: int = 0
    missing_labels: List[str] = field(default_factory=list)
    chunks: List[Path] = field(default_factory=list)


def _copy_pairs(pairs: Sequence[Pair], out_dir: Path,
                progress: Progress = None) -> SubsetResult:
    out_images = out_dir / "images"
    out_labels = out_dir / "labels"
    out_images.mkdir(parents=True, exist_ok=True)
    out_labels.mkdir(parents=True, exist_ok=True)
    res = SubsetResult(output_dir=out_dir)
    total = len(pairs) or 1
    for i, pair in enumerate(pairs):
        if not pair.image:
            continue
        shutil.copy2(pair.image, out_images / pair.image.name)
        if pair.has_label:
            shutil.copy2(pair.label, out_labels / pair.label.name)
        else:
            res.missing_labels.append(pair.image.name)
        res.copied += 1
        _tick(progress, i + 1, total)
    return res


def random_sample(source: DatasetSource, count: int, out_dir: Path,
                  splits: Optional[Iterable[str]] = None, seed: Optional[int] = None,
                  progress: Progress = None) -> SubsetResult:
    """Replaces random_sample.py."""
    pairs = source.pairs(splits)
    if count > len(pairs):
        raise ValueError(f"Asked for {count} images but the dataset only has {len(pairs)}.")
    rng = random.Random(seed)
    return _copy_pairs(rng.sample(pairs, count), out_dir, progress)


def copy_range(source: DatasetSource, start: int, end: int, out_dir: Path,
               splits: Optional[Iterable[str]] = None,
               progress: Progress = None) -> SubsetResult:
    """Replaces image_output_range.py. start/end are 1-based and inclusive."""
    pairs = source.pairs(splits)
    if start < 1 or end > len(pairs) or start > end:
        raise ValueError(
            f"Invalid range {start}-{end}: the dataset has {len(pairs)} images.")
    return _copy_pairs(pairs[start - 1:end], out_dir, progress)


def chunk_dataset(source: DatasetSource, chunk_size: int, out_dir: Path,
                  splits: Optional[Iterable[str]] = None,
                  progress: Progress = None) -> SubsetResult:
    """Replaces split_dataset.py - sequential chunks for batch upload."""
    pairs = source.pairs(splits)
    if chunk_size < 1:
        raise ValueError("Chunk size must be at least 1.")
    n_chunks = math.ceil(len(pairs) / chunk_size) if pairs else 0
    result = SubsetResult(output_dir=out_dir)
    for idx in range(n_chunks):
        chunk = pairs[idx * chunk_size:(idx + 1) * chunk_size]
        chunk_dir = out_dir / f"chunk_{idx + 1}"
        sub = _copy_pairs(chunk, chunk_dir)
        result.copied += sub.copied
        result.missing_labels.extend(sub.missing_labels)
        result.chunks.append(chunk_dir)
        _tick(progress, idx + 1, n_chunks or 1)
    return result


def filter_null(source: DatasetSource, out_dir: Path,
                splits: Optional[Iterable[str]] = None,
                progress: Progress = None) -> SubsetResult:
    """Copy only images that actually have at least one box."""
    keep = [p for p in source.pairs(splits)
            if p.has_label and read_label_file(p.label).boxes]
    return _copy_pairs(keep, out_dir, progress)


# ═══════════════════════════════════════════════════════ review selection ══

REVIEW_ALL = "all"
REVIEW_EMPTY = "empty"
REVIEW_MULTICLASS = "multiclass"
REVIEW_MALFORMED = "malformed"
REVIEW_UNLABELED = "unlabeled"


def collect_for_review(source: DatasetSource, selector,
                       splits: Optional[Iterable[str]] = None) -> List[Pair]:
    """
    Build the working set for review mode.

    `selector` is REVIEW_ALL / REVIEW_EMPTY / REVIEW_MULTICLASS /
    REVIEW_MALFORMED / REVIEW_UNLABELED, or an int class id.
    This is the tab logic from MAIN_label_id_fix_ui.py, generalised.
    """
    out: List[Pair] = []
    for pair in source.pairs(splits):
        if selector == REVIEW_ALL:
            out.append(pair)
            continue
        if selector == REVIEW_UNLABELED:
            if not pair.has_label:
                out.append(pair)
            continue
        if not pair.has_label:
            continue
        lf = read_label_file(pair.label)
        if selector == REVIEW_EMPTY:
            if not lf.boxes:
                out.append(pair)
        elif selector == REVIEW_MALFORMED:
            if lf.malformed:
                out.append(pair)
        elif selector == REVIEW_MULTICLASS:
            if len({b.class_id for b in lf.boxes}) > 1:
                out.append(pair)
        elif isinstance(selector, int):
            if any(b.class_id == selector for b in lf.boxes):
                out.append(pair)
    return out
