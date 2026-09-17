"""ui/label_inspector.py — Inspector dock panel for the selected bounding box."""
from __future__ import annotations
from typing import List, Tuple

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor, QPixmap, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QSpinBox, QPushButton, QCheckBox, QGroupBox, QComboBox,
)


class LabelInspector(QWidget):
    """Read / write properties of the selected BoxItem."""

    deleteRequested      = Signal()
    duplicateRequested   = Signal()
    lockToggled          = Signal(bool)
    classChangeRequested = Signal(int)                 # new class_id
    geometryEdited       = Signal(int, int, int, int)  # x, y, w, h (px)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False
        self._classes: List[Tuple[int, str, str]] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(12)

        # Header / Status
        self._title = QLabel("No box selected")
        pass  # styled by ui/theme.py
        self._title.setWordWrap(True)
        outer.addWidget(self._title)

        # Class selector
        cls_grp = QGroupBox("Class / Category")
        cls_lay = QVBoxLayout(cls_grp)
        cls_lay.setContentsMargins(8, 8, 8, 8)
        self._class_combo = QComboBox()
        self._class_combo.currentIndexChanged.connect(self._on_class_changed)
        cls_lay.addWidget(self._class_combo)
        outer.addWidget(cls_grp)

        # Geometry
        geo_grp = QGroupBox("Coordinates & Size (px)")
        form = QFormLayout(geo_grp)
        form.setContentsMargins(8, 8, 8, 8)
        form.setSpacing(8)
        self._x_spin = self._spin(0, 99999)
        self._y_spin = self._spin(0, 99999)
        self._w_spin = self._spin(1, 99999)
        self._h_spin = self._spin(1, 99999)
        form.addRow("X (Left):", self._x_spin)
        form.addRow("Y (Top):", self._y_spin)
        form.addRow("Width:", self._w_spin)
        form.addRow("Height:", self._h_spin)
        for sp in (self._x_spin, self._y_spin, self._w_spin, self._h_spin):
            sp.editingFinished.connect(self._on_geo_edited)
        outer.addWidget(geo_grp)

        # Actions
        act_grp = QGroupBox("Box Actions")
        act_lay = QVBoxLayout(act_grp)
        act_lay.setContentsMargins(8, 8, 8, 8)
        act_lay.setSpacing(8)

        self._lock_chk = QCheckBox("🔒 Lock Box (prevent edit/drag)")
        self._lock_chk.toggled.connect(self._on_lock)
        act_lay.addWidget(self._lock_chk)

        row = QHBoxLayout()
        self._dup_btn = QPushButton("⧉ Duplicate")
        self._dup_btn.setToolTip("Ctrl+D")
        self._del_btn = QPushButton("Delete")
        self._del_btn.setToolTip("Del / Backspace")
        pass  # styled by ui/theme.py
        self._dup_btn.clicked.connect(self.duplicateRequested)
        self._del_btn.clicked.connect(self.deleteRequested)
        row.addWidget(self._dup_btn)
        row.addWidget(self._del_btn)
        act_lay.addLayout(row)
        outer.addWidget(act_grp)

        outer.addStretch()
        self.setEnabled(False)

    @staticmethod
    def _spin(lo: int, hi: int) -> QSpinBox:
        sp = QSpinBox()
        sp.setRange(lo, hi)
        sp.setButtonSymbols(QSpinBox.NoButtons)
        return sp

    def set_classes(self, classes: List[Tuple[int, str, str]]):
        self._classes = classes
        self._updating = True
        self._class_combo.clear()
        for cid, name, color in classes:
            pix = QPixmap(14, 14)
            pix.fill(QColor(color))
            self._class_combo.addItem(QIcon(pix), f"[{cid}] {name}", userData=cid)
        self._updating = False

    def update_from_box(self, box):
        if box is None:
            self.setEnabled(False)
            self._title.setText("No box selected")
            return
        self.setEnabled(True)
        self._updating = True
        r = box.scene_rect()
        conf_str = f" ({box.confidence:.2f})" if box.confidence is not None else ""
        self._title.setText(f"Selected: {box.class_name}{conf_str}")
        for i in range(self._class_combo.count()):
            if self._class_combo.itemData(i) == box.class_id:
                self._class_combo.setCurrentIndex(i)
                break
        self._x_spin.setValue(int(round(r.x())))
        self._y_spin.setValue(int(round(r.y())))
        self._w_spin.setValue(max(1, int(round(r.width()))))
        self._h_spin.setValue(max(1, int(round(r.height()))))
        self._lock_chk.setChecked(getattr(box, "locked", False))
        self._updating = False

    def _on_class_changed(self, idx: int):
        if self._updating or idx < 0:
            return
        cid = self._class_combo.itemData(idx)
        if cid is not None:
            self.classChangeRequested.emit(cid)

    def _on_geo_edited(self):
        if self._updating:
            return
        self.geometryEdited.emit(
            self._x_spin.value(), self._y_spin.value(),
            self._w_spin.value(), self._h_spin.value(),
        )

    def _on_lock(self, checked: bool):
        if self._updating:
            return
        self.lockToggled.emit(checked)
