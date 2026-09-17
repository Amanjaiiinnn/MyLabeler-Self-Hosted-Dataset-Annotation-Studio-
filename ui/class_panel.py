"""ui/class_panel.py - manage & select the active annotation class."""
from __future__ import annotations
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QInputDialog, QMessageBox, QColorDialog,
)


class ClassPanel(QWidget):
    classSelected = Signal(int)          # class_id
    classesChanged = Signal()            # add/remove/rename/recolor -> caller should refresh canvas lookup

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pm = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        hint = QLabel("<b>Categories</b> (press 0–9 to switch class)")
        pass  # styled by ui/theme.py
        layout.addWidget(hint)

        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.itemDoubleClicked.connect(self._rename_class)
        layout.addWidget(self.list_widget)

        btn_grid = QVBoxLayout()
        btn_grid.setSpacing(4)

        row1 = QHBoxLayout()
        self.add_btn = QPushButton("+ Add Class")
        self.remove_btn = QPushButton("Remove")
        row1.addWidget(self.add_btn)
        row1.addWidget(self.remove_btn)
        btn_grid.addLayout(row1)

        row2 = QHBoxLayout()
        self.rename_btn = QPushButton("Rename")
        self.color_btn = QPushButton("Color")
        row2.addWidget(self.rename_btn)
        row2.addWidget(self.color_btn)
        btn_grid.addLayout(row2)

        layout.addLayout(btn_grid)

        self.add_btn.clicked.connect(self._add_class)
        self.remove_btn.clicked.connect(self._remove_class)
        self.rename_btn.clicked.connect(self._rename_class)
        self.color_btn.clicked.connect(self._change_color)

    def set_project(self, pm):
        self.pm = pm
        self.refresh()

    def refresh(self):
        cur_id = self.current_class_id()
        self.list_widget.clear()
        if not self.pm:
            return
        selected_row = 0
        classes = self.pm.get_classes()
        for idx, (cid, name, color) in enumerate(classes):
            shortcut_hint = f"[{idx}] " if idx < 10 else f"[{cid}] "
            item = QListWidgetItem(f"{shortcut_hint}{name}")
            pix = QPixmap(14, 14)
            pix.fill(QColor(color))
            item.setIcon(QIcon(pix))
            item.setData(Qt.UserRole, cid)
            self.list_widget.addItem(item)
            if cid == cur_id:
                selected_row = idx

        if self.list_widget.count():
            self.list_widget.setCurrentRow(selected_row)
            self.classSelected.emit(self.list_widget.item(selected_row).data(Qt.UserRole))

    def _on_item_clicked(self, item):
        self.classSelected.emit(item.data(Qt.UserRole))

    def select_class_by_index(self, idx: int):
        """Used for number-key shortcuts (0-9)."""
        if 0 <= idx < self.list_widget.count():
            self.list_widget.setCurrentRow(idx)
            self.classSelected.emit(self.list_widget.item(idx).data(Qt.UserRole))

    def current_class_id(self):
        item = self.list_widget.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _add_class(self):
        if not self.pm:
            return
        name, ok = QInputDialog.getText(self, "New Class", "Class name:")
        if ok and name.strip():
            self.pm.add_class(name.strip())
            self.refresh()
            self.classesChanged.emit()

    def _remove_class(self):
        item = self.list_widget.currentItem()
        if not item or not self.pm:
            return
        cid = item.data(Qt.UserRole)
        if QMessageBox.question(
            self, "Remove class",
            f"Remove class '{item.text()}'? Existing boxes with this ID will become unlinked.",
            QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.pm.remove_class(cid)
            self.refresh()
            self.classesChanged.emit()

    def _rename_class(self):
        item = self.list_widget.currentItem()
        if not item or not self.pm:
            return
        cid = item.data(Qt.UserRole)
        classes = self.pm.get_classes()
        current = next((n for i, n, c in classes if i == cid), "")
        name, ok = QInputDialog.getText(self, "Rename Class", "New name:", text=current)
        if ok and name.strip():
            self.pm.rename_class(cid, name.strip())
            self.refresh()
            self.classesChanged.emit()

    def _change_color(self):
        item = self.list_widget.currentItem()
        if not item or not self.pm:
            return
        cid = item.data(Qt.UserRole)
        classes = self.pm.get_classes()
        curr_color_hex = next((c for i, n, c in classes if i == cid), "#7c3aed")
        color = QColorDialog.getColor(QColor(curr_color_hex), self, "Select Class Color")
        if color.isValid():
            self.pm.set_class_color(cid, color.name())
            self.refresh()
            self.classesChanged.emit()

