"""
core/trash.py
Reversible deletes. Nothing in this app calls os.remove on a user's data.

Files are moved into <dataset_root>/.trash/<timestamp>/ keeping their original
relative path, alongside a manifest.json that records where each one came from.
undo_last() puts the most recent batch back exactly where it was.
"""
from __future__ import annotations
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

TRASH_DIRNAME = ".trash"
MANIFEST = "manifest.json"


@dataclass
class TrashBatch:
    batch_id: str
    directory: Path
    entries: List[dict] = field(default_factory=list)
    reason: str = ""

    @property
    def count(self) -> int:
        return len(self.entries)

    @property
    def when(self) -> str:
        try:
            stamp = "_".join(self.batch_id.split("_")[:3])   # drop any collision suffix
            return datetime.strptime(stamp, "%Y%m%d_%H%M%S_%f").strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return self.batch_id


class Trash:
    """Per-dataset-root trash can."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.dir = self.root / TRASH_DIRNAME

    # ------------------------------------------------------------ deleting
    def send(self, paths: Iterable[Path], reason: str = "") -> TrashBatch:
        """Move every existing path into a new trash batch. Never raises on a
        single failure - failures are simply left out of the manifest."""
        paths = [Path(p) for p in paths if p and Path(p).exists()]
        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        batch_dir = self.dir / batch_id
        batch = TrashBatch(batch_id, batch_dir, reason=reason)
        if not paths:
            return batch

        # The Windows clock is coarse enough that two quick deletes get the same
        # timestamp. Sharing a folder would let the second manifest overwrite the
        # first, and restoring would then rmtree files nothing records.
        self.dir.mkdir(parents=True, exist_ok=True)
        n = 0
        while True:
            try:
                batch_dir.mkdir()
                break
            except FileExistsError:
                n += 1
                batch.batch_id = f"{batch_id}_{n:03d}"      # padded so names sort in order
                batch_dir = batch.directory = self.dir / batch.batch_id
        for src in paths:
            try:
                rel = src.resolve().relative_to(self.root)
            except ValueError:
                rel = Path(src.name)                    # outside the root
            dest = batch_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                dest = dest.with_name(f"{dest.stem}__{len(batch.entries)}{dest.suffix}")
            try:
                shutil.move(str(src), str(dest))
            except OSError:
                continue
            batch.entries.append({
                "original": str(src.resolve()),
                "stored": str(dest.relative_to(batch_dir)),
            })

        if not batch.entries:
            try:
                batch_dir.rmdir()
            except OSError:
                pass
            return batch

        (batch_dir / MANIFEST).write_text(
            json.dumps({"batch_id": batch.batch_id, "reason": reason,
                        "entries": batch.entries}, indent=2),
            encoding="utf-8")
        return batch

    # ------------------------------------------------------------ restoring
    def batches(self) -> List[TrashBatch]:
        """Newest first."""
        out: List[TrashBatch] = []
        if not self.dir.is_dir():
            return out
        for d in sorted(self.dir.iterdir(), reverse=True):
            manifest = d / MANIFEST
            if not (d.is_dir() and manifest.is_file()):
                continue
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            out.append(TrashBatch(data.get("batch_id", d.name), d,
                                  data.get("entries", []), data.get("reason", "")))
        return out

    def last_batch(self) -> Optional[TrashBatch]:
        batches = self.batches()
        return batches[0] if batches else None

    def restore(self, batch: TrashBatch) -> int:
        """Move a batch back to where it came from. Returns files restored."""
        restored = 0
        for entry in batch.entries:
            stored = batch.directory / entry["stored"]
            original = Path(entry["original"])
            if not stored.exists() or original.exists():
                continue
            original.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(stored), str(original))
                restored += 1
            except OSError:
                continue
        if restored:
            shutil.rmtree(batch.directory, ignore_errors=True)
        return restored

    def undo_last(self) -> int:
        batch = self.last_batch()
        return self.restore(batch) if batch else 0

    # -------------------------------------------------------------- purging
    def size_bytes(self) -> int:
        if not self.dir.is_dir():
            return 0
        return sum(p.stat().st_size for p in self.dir.rglob("*") if p.is_file())

    def empty(self) -> int:
        """Permanently remove everything in the trash. Returns batches removed."""
        batches = self.batches()
        for b in batches:
            shutil.rmtree(b.directory, ignore_errors=True)
        return len(batches)
