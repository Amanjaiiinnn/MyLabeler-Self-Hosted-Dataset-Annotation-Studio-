"""
tests/conftest.py
Shared fixtures. Every test works inside pytest's tmp_path, so nothing here
ever touches a real project under projects/.
"""
from __future__ import annotations
from pathlib import Path
from typing import Iterable

import pytest
from PIL import Image

from core.project import ProjectManager


def make_image(path: Path, size=(64, 48), color=(120, 80, 40)) -> Path:
    """Write a small solid-colour image; the format follows the extension."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


def write_label(path: Path, lines: Iterable[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = list(lines)
    path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")
    return path


@pytest.fixture
def flat_dataset(tmp_path) -> Path:
    """
    root/images + root/labels with one of each problem the audit looks for:

        good_a     one class-0 box
        good_b     class-0 and class-1 boxes (multiclass)
        empty      label file with no boxes
        nolabel    image with no label file
        broken     one good box and one unparseable line
        outside    box that pokes past the right edge
        orphan     label file with no image
    """
    root = tmp_path / "ds"
    img, lbl = root / "images", root / "labels"
    for stem in ("good_a", "good_b", "empty", "nolabel", "broken", "outside"):
        make_image(img / f"{stem}.jpg")
    write_label(lbl / "good_a.txt", ["0 0.5 0.5 0.2 0.2"])
    write_label(lbl / "good_b.txt", ["0 0.3 0.3 0.1 0.1", "1 0.7 0.7 0.1 0.1"])
    write_label(lbl / "empty.txt", [])
    write_label(lbl / "broken.txt", ["1 0.5 0.5 0.2 0.2", "this is not a box"])
    write_label(lbl / "outside.txt", ["0 0.95 0.5 0.2 0.2"])
    write_label(lbl / "orphan.txt", ["0 0.5 0.5 0.1 0.1"])
    write_label(lbl / "classes.txt", ["cat", "dog"])     # must be ignored as a label
    return root


@pytest.fixture
def project(tmp_path):
    pm = ProjectManager.create(tmp_path, "proj")
    yield pm
    pm.close()


def add_labeled_image(pm: ProjectManager, name: str, lines: Iterable[str],
                      size=(64, 48)) -> str:
    """Drop an image + label straight into a project and index it."""
    make_image(pm.image_path(name), size=size)
    write_label(pm.label_path(name), lines)
    pm._sync_existing_files()
    return name
