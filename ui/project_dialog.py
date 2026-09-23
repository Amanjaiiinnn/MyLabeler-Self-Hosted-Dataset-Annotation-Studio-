"""ui/project_dialog.py - New project creation dialog."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QHBoxLayout,
    QFileDialog, QDialogButtonBox,
)


class NewProjectDialog(QDialog):
    def __init__(self, default_root: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Project")
        self.project_name = ""
        self.project_root = default_root

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit()
        form.addRow("Project name:", self.name_edit)

        root_row = QHBoxLayout()
        self.root_edit = QLineEdit(default_root)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        root_row.addWidget(self.root_edit)
        root_row.addWidget(browse_btn)
        form.addRow("Location:", root_row)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Choose location", self.root_edit.text())
        if path:
            self.root_edit.setText(path)

    def _on_accept(self):
        self.project_name = self.name_edit.text().strip()
        self.project_root = self.root_edit.text().strip()
        if self.project_name:
            self.accept()
