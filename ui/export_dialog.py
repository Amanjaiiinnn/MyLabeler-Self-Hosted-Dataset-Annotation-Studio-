"""ui/export_dialog.py - configure and trigger a train/val YOLO dataset export."""
from __future__ import annotations
from datetime import datetime
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QSpinBox, QCheckBox,
    QDialogButtonBox, QLabel, QMessageBox,
)


class ExportDialog(QDialog):
    def __init__(self, parent=None, default_name: str = "",
                 existing: List[str] | None = None,
                 preprocess_summary: List[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Export Dataset")
        self.setMinimumWidth(420)
        self._existing = set(existing or [])

        if not default_name:
            default_name = "v" + datetime.now().strftime("%Y%m%d_%H%M")
        self.export_name = default_name
        self.val_percent = 20
        self.include_augmented = True

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit(default_name)
        form.addRow("Export folder name:", self.name_edit)

        self.val_spin = QSpinBox()
        self.val_spin.setRange(5, 50)
        self.val_spin.setValue(20)
        self.val_spin.setSuffix(" %")
        form.addRow("Validation split:", self.val_spin)

        self.aug_checkbox = QCheckBox("Include augmented images")
        self.aug_checkbox.setChecked(True)
        self.aug_checkbox.setToolTip(
            "Augmented copies follow their source image into whichever split it "
            "lands in, so no near-duplicate can appear in both train and val.")
        form.addRow(self.aug_checkbox)
        layout.addLayout(form)

        if preprocess_summary:
            note = QLabel("Preprocessing to apply:\n"
                          + "\n".join(f"  • {s}" for s in preprocess_summary))
            note.setWordWrap(True)
            note.setStyleSheet("color: #a3a3a3; font-size: 11px; padding: 6px 0;")
            layout.addWidget(note)

        self.warn_lbl = QLabel("")
        self.warn_lbl.setWordWrap(True)
        self.warn_lbl.setStyleSheet("color: #fca5a5; font-size: 11px;")
        self.warn_lbl.setVisible(False)
        layout.addWidget(self.warn_lbl)
        self.name_edit.textChanged.connect(self._check_name)
        self._check_name(default_name)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _check_name(self, text: str):
        clash = text.strip() in self._existing
        self.warn_lbl.setVisible(clash)
        if clash:
            self.warn_lbl.setText(
                f"⚠ An export named “{text.strip()}” already exists. Continuing "
                f"will delete and rebuild it.")

    def _on_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.information(self, "Name required",
                                    "Give the export folder a name.")
            return
        if name in self._existing:
            answer = QMessageBox.question(
                self, "Overwrite export",
                f"“{name}” already exists and will be deleted and rebuilt.\n\n"
                "Continue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        self.export_name = name
        self.val_percent = self.val_spin.value()
        self.include_augmented = self.aug_checkbox.isChecked()
        self.accept()
