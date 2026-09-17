"""
core/roboflow_sync.py
Upload an exported dataset to a Roboflow project.

The `roboflow` package is imported lazily so the app still starts (and every
local tool still works) when it is not installed.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Signal

from core.workers import CancellableWorker


def is_available() -> bool:
    try:
        import roboflow  # noqa: F401
        return True
    except ImportError:
        return False


@dataclass
class UploadTarget:
    api_key: str
    workspace: str
    project: str
    dataset_path: Path
    project_type: str = "object-detection"
    num_workers: int = 10

    def problems(self) -> List[str]:
        out = []
        if not self.api_key:
            out.append("No Roboflow API key set (Settings, or the ROBOFLOW_API_KEY "
                       "environment variable).")
        if not self.workspace:
            out.append("No workspace set.")
        if not self.project:
            out.append("No project set.")
        if not self.dataset_path or not Path(self.dataset_path).is_dir():
            out.append(f"Dataset folder not found: {self.dataset_path}")
        return out


class RoboflowUploadWorker(CancellableWorker):
    """Uploads a folder; Roboflow's client drives its own progress."""
    finished_ok = Signal(str)

    def __init__(self, target: UploadTarget):
        super().__init__()
        self.target = target

    def run(self):
        problems = self.target.problems()
        if problems:
            self.failed.emit("\n".join(problems))
            return
        try:
            from roboflow import Roboflow
        except ImportError:
            self.failed.emit(
                "The roboflow package is not installed.\n\n"
                "Install it with:\n    pip install roboflow")
            return
        try:
            rf = Roboflow(api_key=self.target.api_key)
            workspace = rf.workspace(self.target.workspace)
            workspace.upload_dataset(
                str(self.target.dataset_path),
                self.target.project,
                project_type=self.target.project_type,
                num_workers=self.target.num_workers,
            )
            self.finished_ok.emit(
                f"Uploaded {self.target.dataset_path.name} to "
                f"{self.target.workspace}/{self.target.project}.")
        except Exception as e:
            self.failed.emit(str(e))
