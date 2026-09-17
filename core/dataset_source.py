"""
core/dataset_source.py
A uniform view over "a YOLO dataset on disk", whatever shape it happens to be.

Handles the three layouts that actually turn up:

    split layout    root/train/images + root/train/labels, plus val|valid|test
    flat layout     root/images + root/labels
    same-dir        root/*.jpg alongside root/*.txt

so the audit, class-remap, subset and review tools can run against the open
project *or* any dataset folder the user points at, without caring which.

Class names come from data.yaml, classes.txt or _darknet.labels when present.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}
SPLIT_ALIASES = {"train": "train", "val": "val", "valid": "val", "validation": "val",
                 "test": "test"}
IGNORED_DIRS = {"augmented", "exports", ".trash", "__pycache__", "runs", "output"}
RESERVED_LABEL_FILES = {"classes.txt", "_darknet.labels", "requirements.txt"}
FLAT_SPLIT = ""          # the single unnamed split used by flat / same-dir layouts

_QUOTE_CHARS = "\"" + chr(39)


@dataclass(frozen=True)
class Pair:
    """One image and the label file that belongs to it (which may not exist)."""
    split: str
    image: Optional[Path]
    label: Optional[Path]

    @property
    def stem(self) -> str:
        p = self.image or self.label
        return p.stem if p else ""

    @property
    def has_image(self) -> bool:
        return self.image is not None and self.image.exists()

    @property
    def has_label(self) -> bool:
        return self.label is not None and self.label.exists()


def _is_image(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS


def _clean(token: str) -> str:
    return token.strip().strip(_QUOTE_CHARS).strip()


class DatasetSource:
    """Read-only index of a dataset folder. Call refresh() after mutating it."""

    def __init__(self, root: Path, label: str = ""):
        self.root = Path(root).resolve()
        self.label = label or self.root.name
        self._dirs: Dict[str, Dict[str, Path]] = {}   # split -> {"images":.., "labels":..}
        self.layout = "unknown"
        self.refresh()

    def __repr__(self) -> str:
        return f"<DatasetSource {self.label} layout={self.layout} splits={self.splits()}>"

    # ------------------------------------------------------------ discovery
    def refresh(self):
        self._dirs.clear()
        self.layout = "unknown"
        if not self.root.is_dir():
            return

        # 1. split layout
        for child in sorted(self.root.iterdir()):
            if not child.is_dir() or child.name.lower() in IGNORED_DIRS:
                continue
            split = SPLIT_ALIASES.get(child.name.lower())
            if not split:
                continue
            imgs, lbls = child / "images", child / "labels"
            if imgs.is_dir() or lbls.is_dir():
                self._dirs[split] = {"images": imgs, "labels": lbls}
        if self._dirs:
            self.layout = "split"
            return

        # 2. flat layout
        imgs, lbls = self.root / "images", self.root / "labels"
        if imgs.is_dir() or lbls.is_dir():
            self._dirs[FLAT_SPLIT] = {"images": imgs, "labels": lbls}
            self.layout = "flat"
            return

        # 3. same-dir layout
        try:
            if any(_is_image(p) for p in self.root.iterdir()):
                self._dirs[FLAT_SPLIT] = {"images": self.root, "labels": self.root}
                self.layout = "same-dir"
        except OSError:
            pass

    @property
    def is_valid(self) -> bool:
        return bool(self._dirs)

    def splits(self) -> List[str]:
        order = {"train": 0, "val": 1, "test": 2, FLAT_SPLIT: 3}
        return sorted(self._dirs.keys(), key=lambda s: order.get(s, 9))

    def split_label(self, split: str) -> str:
        return split.upper() if split else "ALL"

    def images_dir(self, split: str) -> Optional[Path]:
        d = self._dirs.get(split)
        return d["images"] if d else None

    def labels_dir(self, split: str) -> Optional[Path]:
        d = self._dirs.get(split)
        return d["labels"] if d else None

    def label_for(self, split: str, image: Path) -> Optional[Path]:
        ldir = self.labels_dir(split)
        return (ldir / (image.stem + ".txt")) if ldir else None

    # ---------------------------------------------------------------- pairs
    def pairs(self, splits: Optional[Iterable[str]] = None) -> List[Pair]:
        """Every image, paired with its label path (existing or not)."""
        out: List[Pair] = []
        for split in (list(splits) if splits is not None else self.splits()):
            idir, ldir = self.images_dir(split), self.labels_dir(split)
            if not idir or not idir.is_dir():
                continue
            for img in sorted(idir.iterdir()):
                if _is_image(img):
                    out.append(Pair(split, img, (ldir / (img.stem + ".txt")) if ldir else None))
        return out

    def label_files(self, splits: Optional[Iterable[str]] = None) -> List[Path]:
        out: List[Path] = []
        for split in (list(splits) if splits is not None else self.splits()):
            ldir = self.labels_dir(split)
            if ldir and ldir.is_dir():
                out.extend(sorted(p for p in ldir.glob("*.txt")
                                  if p.name not in RESERVED_LABEL_FILES))
        return out

    def orphan_labels(self, splits: Optional[Iterable[str]] = None) -> List[Pair]:
        """Label files with no matching image."""
        out: List[Pair] = []
        for split in (list(splits) if splits is not None else self.splits()):
            idir, ldir = self.images_dir(split), self.labels_dir(split)
            if not ldir or not ldir.is_dir():
                continue
            stems = set()
            if idir and idir.is_dir():
                stems = {p.stem for p in idir.iterdir() if _is_image(p)}
            for lbl in sorted(ldir.glob("*.txt")):
                if lbl.name in RESERVED_LABEL_FILES:
                    continue
                if lbl.stem not in stems:
                    out.append(Pair(split, None, lbl))
        return out

    # -------------------------------------------------------------- classes
    def class_names(self) -> Dict[int, str]:
        """Best-effort class map from data.yaml / classes.txt / _darknet.labels."""
        for finder in (self._names_from_yaml, self._names_from_txt):
            names = finder()
            if names:
                return names
        return {}

    def _candidate_files(self, *filenames: str) -> List[Path]:
        out = [self.root / f for f in filenames]
        out += [self.root.parent / f for f in filenames]
        for split in self.splits():
            ldir = self.labels_dir(split)
            if ldir:
                out += [ldir / f for f in filenames]
        return [p for p in out if p.is_file()]

    def _names_from_yaml(self) -> Dict[int, str]:
        for path in self._candidate_files("data.yaml", "data.yml"):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            names = parse_yaml_names(text)
            if names:
                return names
        return {}

    def _names_from_txt(self) -> Dict[int, str]:
        for path in self._candidate_files("classes.txt", "_darknet.labels"):
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            names = {i: n.strip() for i, n in enumerate(lines)
                     if n.strip() and n.strip() != "__unused__"}
            if names:
                return names
        return {}


def parse_yaml_names(text: str) -> Dict[int, str]:
    """
    Minimal `names:` reader so we do not depend on PyYAML. Handles the inline
    forms `names: [a, b]` and `names: {0: a}` as well as the indented block form.
    """
    names: Dict[int, str] = {}
    lines = text.splitlines()
    for i, raw in enumerate(lines):
        if not re.match(r"^\s*names\s*:", raw):
            continue
        inline = raw.split(":", 1)[1].strip()
        if inline.startswith("["):
            items = [_clean(s) for s in inline.strip("[]").split(",")]
            return {idx: n for idx, n in enumerate(items) if n}
        if inline.startswith("{"):
            for chunk in inline.strip("{}").split(","):
                if ":" in chunk:
                    k, v = chunk.split(":", 1)
                    try:
                        names[int(_clean(k))] = _clean(v)
                    except ValueError:
                        pass
            return names
        # block form
        idx = 0
        for follow in lines[i + 1:]:
            if not follow.strip():
                continue
            if not follow.startswith((" ", "\t")):
                break
            item = follow.strip()
            if item.startswith("- "):
                names[idx] = _clean(item[2:])
                idx += 1
            elif ":" in item:
                k, v = item.split(":", 1)
                try:
                    names[int(_clean(k))] = _clean(v)
                except ValueError:
                    break
            else:
                break
        return names
    return names


def source_for_project(pm) -> DatasetSource:
    """A DatasetSource over the open project's images/ + labels/ folders."""
    return DatasetSource(pm.root, label=pm.root.name)
