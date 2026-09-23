"""
core/project.py
Project = a folder on disk containing:

    my_project/
        project.db        <- SQLite metadata (images, classes, status)
        images/           <- original imported images
        labels/           <- YOLO .txt annotation files (same basename as image)
        augmented/
            images/
            labels/
        classes.txt       <- one class name per line, index = class_id
        exports/          <- final train/val split datasets land here

ProjectManager is the single source of truth used by the UI.
"""
from __future__ import annotations
import shutil
import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple, Set

from PIL import Image

SCHEMA = """
CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT UNIQUE NOT NULL,
    width INTEGER,
    height INTEGER,
    status TEXT DEFAULT 'unlabeled',  -- unlabeled | labeled | auto-labeled
    split TEXT DEFAULT ''             -- train | valid | test | '' (unassigned)
);

CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY,           -- also acts as YOLO class_id, assigned manually
    name TEXT UNIQUE NOT NULL,
    color TEXT DEFAULT '#ff3b30'
);
"""

DEFAULT_COLORS = [
    "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231",
    "#911eb4", "#46f0f0", "#f032e6", "#bcf60c", "#fabebe",
    "#008080", "#e6beff", "#9a6324", "#fffac8", "#800000",
    "#a78bfa", "#38bdf8", "#4ade80", "#fb923c", "#f43f5e",
]

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}

# .txt files that are never YOLO label files and must not be adopted as one.
RESERVED_TXT_FILES = {"classes.txt", "requirements.txt", "_darknet.labels",
                      "readme.txt", "notes.txt", "license.txt"}


class ProjectManager:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.images_dir = self.root / "images"
        self.labels_dir = self.root / "labels"
        self.aug_images_dir = self.root / "augmented" / "images"
        self.aug_labels_dir = self.root / "augmented" / "labels"
        self.exports_dir = self.root / "exports"
        self.db_path = self.root / "project.db"
        self._conn: Optional[sqlite3.Connection] = None

    # ---------------------------------------------------------------- setup
    @classmethod
    def create(cls, root: Path, name: str) -> "ProjectManager":
        project_dir = Path(root) / name
        project_dir.mkdir(parents=True, exist_ok=False)
        pm = cls(project_dir)
        pm._ensure_dirs()
        pm.connect()
        pm._ensure_schema()
        (pm.root / "classes.txt").touch()
        return pm

    @classmethod
    def open(cls, root: Path, adopt_loose_files: bool = False) -> "ProjectManager":
        """
        Open an existing project, or adopt a plain dataset folder as one.

        `adopt_loose_files` controls whether images and .txt files sitting
        directly in the folder are MOVED into images/ and labels/. It defaults
        to False so that opening the wrong folder can never rearrange it - the
        UI asks first and passes True only after the user confirms.
        """
        pm = cls(Path(root))
        pm._ensure_dirs()
        if not pm.db_path.exists():
            pm.auto_init(move_files=adopt_loose_files)
        else:
            pm.connect()
            pm._ensure_schema()
            pm._sync_existing_files()
        return pm

    @staticmethod
    def scan_loose_files(root: Path) -> Tuple[List[Path], List[Path]]:
        """
        Report which files `open(..., adopt_loose_files=True)` would relocate,
        so the UI can show a count before anything moves.
        """
        root = Path(root)
        images, labels = [], []
        if not root.is_dir():
            return images, labels
        for p in root.iterdir():
            if not p.is_file():
                continue
            if p.suffix.lower() in IMAGE_EXTENSIONS:
                images.append(p)
            elif p.suffix.lower() == ".txt" and p.name not in RESERVED_TXT_FILES:
                labels.append(p)
        return images, labels

    def _ensure_dirs(self):
        for d in (self.images_dir, self.labels_dir, self.aug_images_dir,
                  self.aug_labels_dir, self.exports_dir):
            d.mkdir(parents=True, exist_ok=True)

    def connect(self):
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    def _ensure_schema(self):
        if not self._conn:
            return
        self._conn.executescript(SCHEMA)
        # Older projects predate the split column; add it rather than making
        # the user rebuild the project.
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(images)")}
        if "split" not in cols:
            self._conn.execute("ALTER TABLE images ADD COLUMN split TEXT DEFAULT ''")
        self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()

    def auto_init(self, move_files: bool = False):
        """
        Initialize a project from an existing directory of images and/or YOLO
        labels. Files already inside images/ and labels/ are always indexed;
        loose files in the folder root are only relocated when move_files=True.
        """
        self._ensure_dirs()
        self.connect()
        self._ensure_schema()

        # 1. Discover classes from classes.txt or data.yaml
        classes_txt = self.root / "classes.txt"
        if classes_txt.exists():
            lines = [line.strip() for line in classes_txt.read_text(encoding="utf-8", errors="ignore").splitlines()]
            for idx, name in enumerate(lines):
                if name and name != "__unused__":
                    self._insert_class_if_missing(idx, name)

        # 2. Adopt loose images sitting in the folder root (opt-in only)
        if move_files:
            for p in list(self.root.iterdir()):
                if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
                    dest = self.images_dir / p.name
                    if dest != p and not dest.exists():
                        shutil.move(str(p), str(dest))

            # 3. Adopt loose label files, but never a known non-label .txt
            for p in list(self.root.iterdir()):
                if p.is_file() and p.suffix.lower() == ".txt" and p.name not in RESERVED_TXT_FILES:
                    dest = self.labels_dir / p.name
                    if dest != p and not dest.exists():
                        shutil.move(str(p), str(dest))

            # A combined "one line per box, prefixed by image name" file
            for special_txt in ("label.txt", "labels.txt", "annotations.txt"):
                sp = self.labels_dir / special_txt
                if sp.exists():
                    self._parse_combined_label_file(sp)

        # 4. Infer unknown classes from label files
        known_class_ids = set(c[0] for c in self.get_classes())
        found_class_ids = self._scan_class_ids_from_labels()
        for cid in sorted(found_class_ids):
            if cid not in known_class_ids:
                self._insert_class_if_missing(cid, f"class{cid}")

        # 5. Populate images table
        self._sync_existing_files()
        self._write_classes_txt()

    def _sync_existing_files(self):
        """Ensure all images in images_dir exist in SQLite database with correct status."""
        for p in self.images_dir.iterdir():
            if not p.is_file() or p.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            row = self.get_image(p.name)
            lbl = self.label_path(p.name)
            has_boxes = lbl.exists() and lbl.stat().st_size > 0
            expected_status = "labeled" if has_boxes else "unlabeled"

            if row is None:
                try:
                    with Image.open(p) as im:
                        w, h = im.size
                except Exception:
                    w, h = 0, 0
                try:
                    self._conn.execute(
                        "INSERT INTO images (filename, width, height, status) VALUES (?,?,?,?)",
                        (p.name, w, h, expected_status))
                except sqlite3.IntegrityError:
                    pass
            else:
                if row["status"] == "unlabeled" and has_boxes:
                    self.set_status(p.name, "labeled")
        self._conn.commit()

    def _scan_class_ids_from_labels(self) -> Set[int]:
        ids = set()
        if not self.labels_dir.exists():
            return ids
        for p in self.labels_dir.glob("*.txt"):
            try:
                for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                    parts = line.strip().split()
                    if parts and parts[0].isdigit():
                        ids.add(int(parts[0]))
            except Exception:
                continue
        return ids

    def _parse_combined_label_file(self, txt_file: Path):
        """Parse files where each line is: `image_name.jpg class_id xc yc w h`."""
        try:
            lines = txt_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            grouped: dict = {}
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 6 and (parts[0].lower().endswith(tuple(IMAGE_EXTENSIONS)) or "/" in parts[0] or "\\" in parts[0]):
                    img_name = Path(parts[0]).name
                    yolo_line = " ".join(parts[1:6])
                    grouped.setdefault(img_name, []).append(yolo_line)
                elif len(parts) == 5 and parts[0].isdigit():
                    # Standard line without image name (skip if we can't map)
                    pass
            for img_name, yolo_lines in grouped.items():
                lbl_path = self.labels_dir / (Path(img_name).stem + ".txt")
                lbl_path.write_text("\n".join(yolo_lines) + "\n", encoding="utf-8")
        except Exception:
            pass

    def _insert_class_if_missing(self, class_id: int, name: str):
        color = DEFAULT_COLORS[class_id % len(DEFAULT_COLORS)]
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO classes (id, name, color) VALUES (?,?,?)",
                (class_id, name, color))
            self._conn.commit()
        except Exception:
            pass

    # -------------------------------------------------------------- classes
    def get_classes(self) -> List[Tuple[int, str, str]]:
        rows = self._conn.execute("SELECT id, name, color FROM classes ORDER BY id").fetchall()
        return [(r["id"], r["name"], r["color"]) for r in rows]

    def add_class(self, name: str, color: Optional[str] = None) -> int:
        existing = self._conn.execute("SELECT id FROM classes").fetchall()
        next_id = max([r["id"] for r in existing], default=-1) + 1
        if not color:
            color = DEFAULT_COLORS[next_id % len(DEFAULT_COLORS)]
        self._conn.execute("INSERT INTO classes (id, name, color) VALUES (?,?,?)",
                           (next_id, name, color))
        self._conn.commit()
        self._write_classes_txt()
        return next_id

    def remove_class(self, class_id: int):
        self._conn.execute("DELETE FROM classes WHERE id=?", (class_id,))
        self._conn.commit()
        self._write_classes_txt()

    def rename_class(self, class_id: int, new_name: str):
        self._conn.execute("UPDATE classes SET name=? WHERE id=?", (new_name, class_id))
        self._conn.commit()
        self._write_classes_txt()

    def set_class_color(self, class_id: int, new_color: str):
        self._conn.execute("UPDATE classes SET color=? WHERE id=?", (new_color, class_id))
        self._conn.commit()

    # Names the UI already calls; kept as the canonical spelling for new code.
    update_class_color = set_class_color
    delete_class = remove_class

    def ensure_class(self, class_id: int, name: Optional[str] = None) -> bool:
        """Register a class id if it is not known yet. Returns True if added."""
        if any(c[0] == class_id for c in self.get_classes()):
            return False
        self._insert_class_if_missing(class_id, name or f"class{class_id}")
        self._write_classes_txt()
        return True

    def sync_classes_from_labels(self, names_hint: Optional[dict] = None) -> List[int]:
        """
        Make sure every class id that appears in a label file exists in the
        classes table. Auto-labeling writes the *model's* class indices, so
        without this a COCO prediction of class 9 lands in the dataset with no
        name, no colour, and an out-of-range entry in the exported data.yaml.

        `names_hint` maps id -> name (e.g. the loaded model's class names).
        Returns the ids that were newly registered.
        """
        known = {c[0] for c in self.get_classes()}
        found = self._scan_class_ids_from_labels()
        added = []
        for cid in sorted(found - known):
            name = (names_hint or {}).get(cid) or f"class{cid}"
            self._insert_class_if_missing(cid, name)
            added.append(cid)
        if added:
            self._write_classes_txt()
        return added

    def _write_classes_txt(self):
        classes = self.get_classes()
        if not classes:
            (self.root / "classes.txt").write_text("", encoding="utf-8")
            return
        max_id = max([c[0] for c in classes], default=-1)
        lines = ["__unused__"] * (max_id + 1)
        for cid, name, _ in classes:
            lines[cid] = name
        (self.root / "classes.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # --------------------------------------------------------------- images
    def import_images(self, paths: List[str]) -> int:
        """Import a list of image paths. If a corresponding .txt exists in the source folder, import it as label too!"""
        added = 0
        for p_str in paths:
            p = Path(p_str)
            if not p.exists() or p.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            dest = self.images_dir / p.name
            if not dest.exists():
                shutil.copy2(p, dest)
            try:
                with Image.open(dest) as im:
                    w, h = im.size
            except Exception:
                w, h = 0, 0

            # Check for label file:
            # 1. in same directory: <stem>.txt
            # 2. in sibling labels/ directory: ../labels/<stem>.txt
            # 3. in labels/ subdirectory: ./labels/<stem>.txt
            found_label = None
            same_dir_txt = p.parent / (p.stem + ".txt")
            sibling_labels_txt = p.parent.parent / "labels" / (p.stem + ".txt")
            sub_labels_txt = p.parent / "labels" / (p.stem + ".txt")

            for cand in (same_dir_txt, sibling_labels_txt, sub_labels_txt):
                if cand.exists() and cand.is_file():
                    found_label = cand
                    break

            target_label = self.label_path(p.name)
            if found_label and not target_label.exists():
                shutil.copy2(found_label, target_label)

            has_boxes = target_label.exists() and target_label.stat().st_size > 0
            status = "labeled" if has_boxes else "unlabeled"

            try:
                self._conn.execute(
                    "INSERT OR REPLACE INTO images (filename, width, height, status) VALUES (?,?,?,?)",
                    (p.name, w, h, status))
                added += 1
            except sqlite3.IntegrityError:
                pass

        # Also register any new classes discovered in labels
        known_ids = set(c[0] for c in self.get_classes())
        found_ids = self._scan_class_ids_from_labels()
        for cid in sorted(found_ids):
            if cid not in known_ids:
                self._insert_class_if_missing(cid, f"class{cid}")

        self._conn.commit()
        self._write_classes_txt()
        return added

    def import_folder(self, folder_path: str) -> dict:
        """
        Import every image, label and class name found in a folder.

        A train/valid/test layout is detected and each image keeps the split it
        arrived in, so re-importing an exported dataset round-trips instead of
        being flattened into one undifferentiated pile.
        """
        src = Path(folder_path)
        if not src.exists() or not src.is_dir():
            return {"images": 0, "total_found": 0, "splits": {}}

        # class names, if the folder ships any
        for name_file in ("classes.txt", "_darknet.labels"):
            candidate = src / name_file
            if candidate.exists():
                lines = [l.strip() for l in candidate.read_text(
                    encoding="utf-8", errors="ignore").splitlines()]
                for idx, name in enumerate(lines):
                    if name and name != "__unused__":
                        self._insert_class_if_missing(idx, name)
                break

        from core.dataset_source import DatasetSource
        source = DatasetSource(src)

        split_of: dict = {}
        img_paths: List[str] = []
        if source.is_valid:
            for pair in source.pairs():
                if not pair.image:
                    continue
                img_paths.append(str(pair.image))
                if pair.split:
                    split_of[pair.image.name] = (
                        "valid" if pair.split == "val" else pair.split)
        else:
            # not a recognised layout - fall back to sweeping for images
            found = []
            for ext in IMAGE_EXTENSIONS:
                found.extend(src.rglob(f"*{ext}"))
                found.extend(src.rglob(f"*{ext.upper()}"))
            img_paths = sorted({str(p) for p in found})

        added = self.import_images(img_paths)

        applied = {}
        for split in self.SPLITS:
            names = [n for n, sp in split_of.items() if sp == split]
            if names:
                self.set_splits(names, split)
                applied[split] = len(names)

        return {"images": added, "total_found": len(img_paths),
                "splits": applied, "layout": source.layout if source.is_valid else "flat"}

    def get_images(self, filter_text: str = "", filter_status: str = "all",
                   filter_split: str = "all") -> List[sqlite3.Row]:
        query = "SELECT * FROM images WHERE 1=1"
        params = []
        if filter_text:
            query += " AND filename LIKE ?"
            params.append(f"%{filter_text}%")
        if filter_status and filter_status != "all":
            query += " AND status = ?"
            params.append(filter_status)
        if filter_split and filter_split != "all":
            query += " AND COALESCE(split,'') = ?"
            params.append("" if filter_split == "default" else filter_split)
        query += " ORDER BY filename"
        return self._conn.execute(query, params).fetchall()

    def get_image(self, filename: str) -> Optional[sqlite3.Row]:
        return self._conn.execute("SELECT * FROM images WHERE filename=?", (filename,)).fetchone()

    def set_status(self, filename: str, status: str):
        self._conn.execute("UPDATE images SET status=? WHERE filename=?", (status, filename))
        self._conn.commit()

    def trash(self):
        """Lazily-built trash can for this project."""
        from core.trash import Trash
        if getattr(self, "_trash", None) is None:
            self._trash = Trash(self.root)
        return self._trash

    def delete_image(self, filename: str) -> int:
        """Send one image + its label to .trash/ (recoverable) and de-index it."""
        return self.delete_images([filename])

    def delete_images(self, filenames: List[str], reason: str = "deleted from dataset") -> int:
        """Batch delete as a single undoable trash entry. Returns files trashed."""
        victims: List[Path] = []
        for filename in filenames:
            for p in (self.image_path(filename), self.label_path(filename)):
                if p.exists():
                    victims.append(p)
            self._conn.execute("DELETE FROM images WHERE filename=?", (filename,))
        self._conn.commit()
        return self.trash().send(victims, reason=reason).count

    def undo_last_delete(self) -> int:
        """Restore the most recent trash batch and re-index whatever came back."""
        restored = self.trash().undo_last()
        if restored:
            self._sync_existing_files()
        return restored

    def image_path(self, filename: str) -> Path:
        return self.images_dir / filename

    def label_path(self, filename: str) -> Path:
        return self.labels_dir / (Path(filename).stem + ".txt")

    def count_boxes(self, filename: str) -> int:
        lp = self.label_path(filename)
        if not lp.exists():
            return 0
        try:
            return sum(1 for line in lp.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip())
        except Exception:
            return 0

    # ---------------------------------------------------------------- splits
    SPLITS = ("train", "valid", "test")

    def set_split(self, filename: str, split: str):
        """split is 'train' | 'valid' | 'test' | '' (unassigned)."""
        split = split if split in self.SPLITS else ""
        self._conn.execute("UPDATE images SET split=? WHERE filename=?",
                           (split, filename))
        self._conn.commit()

    def set_splits(self, filenames: List[str], split: str) -> int:
        split = split if split in self.SPLITS else ""
        self._conn.executemany("UPDATE images SET split=? WHERE filename=?",
                               [(split, f) for f in filenames])
        self._conn.commit()
        return len(filenames)

    def split_counts(self) -> dict:
        """Counts per split, with unassigned images reported as 'default'."""
        rows = self._conn.execute(
            "SELECT COALESCE(split,'') s, COUNT(*) c FROM images GROUP BY s"
        ).fetchall()
        out = {"train": 0, "valid": 0, "test": 0, "default": 0}
        for r in rows:
            key = r["s"] if r["s"] in self.SPLITS else "default"
            out[key] += r["c"]
        out["all"] = sum(out[k] for k in ("train", "valid", "test", "default"))
        return out

    def rebalance_splits(self, train: float = 0.7, valid: float = 0.2,
                         test: float = 0.1, seed: int = 42,
                         only_unassigned: bool = False) -> dict:
        """
        Deal images into train/valid/test.

        Ratios are normalised, so 70/20/10 and 7/2/1 behave identically. Pass
        only_unassigned=True to leave images you have already placed by hand.
        """
        import random
        total_ratio = train + valid + test
        if total_ratio <= 0:
            raise ValueError("Split ratios must add up to more than zero.")
        train, valid, test = (train / total_ratio, valid / total_ratio,
                              test / total_ratio)

        rows = self.get_images(filter_split="default" if only_unassigned else "all")
        names = [r["filename"] for r in rows]
        random.Random(seed).shuffle(names)

        n = len(names)
        n_train = int(round(n * train))
        n_valid = int(round(n * valid))
        # whatever rounding leaves over goes to test, so nothing is dropped
        chunks = {
            "train": names[:n_train],
            "valid": names[n_train:n_train + n_valid],
            "test": names[n_train + n_valid:],
        }
        for split, group in chunks.items():
            if group:
                self.set_splits(group, split)
        return {k: len(v) for k, v in chunks.items()}

    def images_for_split(self, split: str) -> List[str]:
        return [r["filename"] for r in self.get_images(filter_split=split)]

    # ------------------------------------------------------------- metadata
    @staticmethod
    def describe(root: Path) -> dict:
        """
        Summarise a project folder cheaply, for the Projects grid — without
        opening the database or loading any image.
        """
        root = Path(root)
        images_dir = root / "images"
        thumb = None
        count = 0
        newest = root.stat().st_mtime if root.exists() else 0.0
        if images_dir.is_dir():
            for entry in sorted(images_dir.iterdir()):
                if entry.is_file() and entry.suffix.lower() in IMAGE_EXTENSIONS:
                    count += 1
                    if thumb is None:
                        thumb = entry
        for probe in (root / "project.db", root / "labels", images_dir):
            try:
                newest = max(newest, probe.stat().st_mtime)
            except OSError:
                pass

        classes: List[str] = []
        ctxt = root / "classes.txt"
        if ctxt.is_file():
            try:
                classes = [line.strip() for line
                           in ctxt.read_text(encoding="utf-8", errors="replace").splitlines()
                           if line.strip() and line.strip() != "__unused__"]
            except OSError:
                pass

        n_versions = 0
        exports = root / "exports"
        if exports.is_dir():
            n_versions = sum(1 for p in exports.iterdir() if p.is_dir())

        return {
            "name": root.name,
            "path": root,
            "images": count,
            "classes": classes,
            "versions": n_versions,
            "thumbnail": thumb,
            "modified": newest,
            "is_project": (root / "project.db").is_file() or count > 0,
        }

    @staticmethod
    def list_projects(root: Path) -> List[dict]:
        """Every project folder under `root`, newest first."""
        root = Path(root)
        if not root.is_dir():
            return []
        out = []
        for child in root.iterdir():
            if not child.is_dir() or child.name.startswith("."):
                continue
            info = ProjectManager.describe(child)
            out.append(info)
        out.sort(key=lambda d: d["modified"], reverse=True)
        return out

    def stats(self) -> dict:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) c FROM images GROUP BY status").fetchall()
        counts = {r["status"]: r["c"] for r in rows}
        total = sum(counts.values())
        return {
            "total": total,
            "labeled": counts.get("labeled", 0),
            "auto-labeled": counts.get("auto-labeled", 0),
            "unlabeled": counts.get("unlabeled", 0),
        }

