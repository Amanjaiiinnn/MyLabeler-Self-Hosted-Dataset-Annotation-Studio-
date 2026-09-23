"""
ui/rebalance_dialog.py — deal every image into train / valid / test.

Ratios are normalised, so 70/20/10 and 7/2/1 behave the same; the preview shows
the actual image counts you will get before anything is written.
"""
from __future__ import annotations
from typing import Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QDialogButtonBox, QGridLayout,
)

from ui.theme import T, mono_font
from ui.widgets import (
    Banner, button, primary_button, spin, check, mono_label, hrule, Meter,
)


class RebalanceDialog(QDialog):
    def __init__(self, parent=None, total: int = 0,
                 counts: Dict[str, int] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Rebalance splits")
        self.setMinimumWidth(440)
        self.total = total
        counts = counts or {}

        self.train = 0.7
        self.valid = 0.2
        self.test = 0.1
        self.seed = 42
        self.only_unassigned = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(T.S5, T.S4, T.S5, T.S4)
        lay.setSpacing(T.S3)

        head = QLabel("Rebalance splits")
        head.setObjectName("Display")
        lay.addWidget(head)

        current = mono_label(
            f"now: train {counts.get('train', 0):,} · valid {counts.get('valid', 0):,} "
            f"· test {counts.get('test', 0):,} · unassigned "
            f"{counts.get('default', 0):,}", T.FS_SMALL, T.TX_3)
        lay.addWidget(current)
        lay.addWidget(hrule())

        grid = QGridLayout()
        grid.setHorizontalSpacing(T.S3)
        grid.setVerticalSpacing(T.S2)
        self.spins = {}
        for row, (key, label, default, color) in enumerate((
                ("train", "Train", 70, T.ACCENT),
                ("valid", "Valid", 20, T.OK),
                ("test", "Test", 10, T.WARN))):
            name = QLabel(label)
            name.setStyleSheet(f"color:{T.TX_1};font-size:{T.FS_CONTROL}px;")
            sp = spin(0, 100, default, " %", width=84)
            sp.valueChanged.connect(lambda _=0: self._update_preview())
            meter = Meter(color, default / 100)
            out = mono_label("", T.FS_SMALL, T.TX_2)
            out.setFixedWidth(90)
            out.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(name, row, 0)
            grid.addWidget(sp, row, 1)
            grid.addWidget(meter, row, 2)
            grid.addWidget(out, row, 3)
            grid.setColumnStretch(2, 1)
            self.spins[key] = (sp, meter, out)
        lay.addLayout(grid)

        opts = QHBoxLayout()
        opts.setSpacing(T.S3)
        self.only_chk = check("Only images that have no split yet")
        self.only_chk.setToolTip(
            "Leave anything you have already assigned by hand exactly where it is")
        self.only_chk.toggled.connect(lambda _: self._update_preview())
        opts.addWidget(self.only_chk)
        opts.addStretch()
        seed_lbl = QLabel("Seed")
        seed_lbl.setObjectName("Muted")
        opts.addWidget(seed_lbl)
        self.seed_spin = spin(0, 999999, 42, width=86)
        self.seed_spin.setToolTip("Same seed gives the same split every time")
        opts.addWidget(self.seed_spin)
        lay.addLayout(opts)

        self.note = Banner("", "info", "check")
        lay.addWidget(self.note)

        buttons = QDialogButtonBox()
        self.ok_btn = primary_button("Rebalance", icon_name="layers")
        cancel = button("Cancel")
        cancel.clicked.connect(self.reject)
        self.ok_btn.clicked.connect(self._on_accept)
        buttons.addButton(cancel, QDialogButtonBox.RejectRole)
        buttons.addButton(self.ok_btn, QDialogButtonBox.AcceptRole)
        lay.addWidget(buttons)

        self._counts = counts
        self._update_preview()

    def _ratios(self):
        t = self.spins["train"][0].value()
        v = self.spins["valid"][0].value()
        s = self.spins["test"][0].value()
        return t, v, s

    def _pool(self) -> int:
        if self.only_chk.isChecked():
            return self._counts.get("default", 0)
        return self.total

    def _update_preview(self):
        t, v, s = self._ratios()
        total_ratio = t + v + s
        pool = self._pool()
        self.ok_btn.setEnabled(total_ratio > 0 and pool > 0)

        if total_ratio <= 0:
            self.note.set_text("Ratios add up to zero — nothing to deal.")
            for key in self.spins:
                self.spins[key][1].set_fraction(0)
                self.spins[key][2].setText("—")
            return

        n_train = int(round(pool * t / total_ratio))
        n_valid = int(round(pool * v / total_ratio))
        n_test = pool - n_train - n_valid
        for key, n in (("train", n_train), ("valid", n_valid), ("test", n_test)):
            sp, meter, out = self.spins[key]
            meter.set_fraction((sp.value() / total_ratio) if total_ratio else 0)
            out.setText(f"{max(0, n):,} imgs")

        if pool == 0:
            self.note.set_text("Every image already has a split assigned.")
        elif total_ratio != 100:
            self.note.set_text(
                f"Ratios add up to {total_ratio}, so they are scaled to fit. "
                f"{pool:,} image(s) will be dealt out.")
        else:
            self.note.set_text(
                f"{pool:,} image(s) will be dealt out. Images already assigned "
                f"by hand are "
                + ("kept as they are." if self.only_chk.isChecked()
                   else "reassigned too."))

    def _on_accept(self):
        t, v, s = self._ratios()
        if t + v + s <= 0:
            return
        self.train, self.valid, self.test = float(t), float(v), float(s)
        self.seed = self.seed_spin.value()
        self.only_unassigned = self.only_chk.isChecked()
        self.accept()
