"""
ui/preprocessing_dialog.py — pick a preprocessing step.

Only steps that the exporter actually applies are offered. The previous version
listed ten options, five of which silently did nothing; the ones that are not
implemented here are named, greyed out, and point at where the equivalent bulk
operation does exist.
"""
from __future__ import annotations
from typing import Optional, Set

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame,
    QDialogButtonBox, QWidget,
)

from ui.theme import T
from ui.icons import icon
from ui.widgets import Banner, hrule

# key, title, one-line description, icon
AVAILABLE = [
    ("resize",        "Resize",         "Letterbox to 640×640, aspect preserved", "fit"),
    ("grayscale",     "Grayscale",      "Convert to single channel",              "layers"),
    ("contrast",      "Auto-contrast",  "CLAHE luminance equalisation",           "eye"),
    ("filter_null",   "Filter null",    "Drop images with no boxes",              "trash"),
    ("random_sample", "Random sample",  "Keep a random 50%",                      "grid"),
]

# key, title, where the equivalent lives instead
ELSEWHERE = [
    ("Tile",            "not implemented"),
    ("Isolate objects",  "not implemented"),
    ("Static crop",      "not implemented"),
    ("Modify classes",   "Tools → Class tools"),
    ("Filter by tag",    "tags are not stored yet"),
]


class StepCard(QFrame):
    chosen = Signal(str)

    def __init__(self, key: str, title: str, detail: str, icon_name: str,
                 disabled: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("StepCard")
        self.key = key
        self._disabled = disabled
        self.setFixedSize(212, 76)
        if not disabled:
            self.setCursor(Qt.PointingHandCursor)
        self._apply(False)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(T.S3, T.S3, T.S3, T.S3)
        lay.setSpacing(T.S3)

        glyph = QLabel()
        color = T.TX_4 if disabled else T.ACCENT
        glyph.setPixmap(icon(icon_name, color, 16).pixmap(16, 16))
        glyph.setFixedSize(32, 32)
        glyph.setAlignment(Qt.AlignCenter)
        glyph.setStyleSheet(
            f"background:{T.INK_800 if disabled else T.ACCENT_WASH};"
            f"border-radius:{T.R_SM}px;border:none;")
        lay.addWidget(glyph, alignment=Qt.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet(
            f"color:{T.TX_4 if disabled else T.TX_1};font-size:{T.FS_CONTROL}px;"
            f"font-weight:600;background:transparent;border:none;")
        d = QLabel(detail)
        d.setWordWrap(True)
        d.setStyleSheet(
            f"color:{T.TX_4 if disabled else T.TX_3};font-size:{T.FS_SMALL}px;"
            f"background:transparent;border:none;")
        col.addWidget(t)
        col.addWidget(d)
        col.addStretch()
        lay.addLayout(col, stretch=1)

    def _apply(self, hot: bool):
        if self._disabled:
            self.setStyleSheet(
                f"QFrame#StepCard{{background:{T.INK_850};border:1px dashed {T.LINE};"
                f"border-radius:{T.R}px;}}")
            return
        self.setStyleSheet(
            f"QFrame#StepCard{{background:{T.INK_800 if not hot else T.INK_750};"
            f"border:1px solid {T.ACCENT if hot else T.LINE_2};"
            f"border-radius:{T.R}px;}}")

    def enterEvent(self, event):
        self._apply(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if not self._disabled and event.button() == Qt.LeftButton:
            self.chosen.emit(self.key)
        super().mousePressEvent(event)


class PreprocessingDialog(QDialog):
    def __init__(self, parent=None, already: Optional[Set[str]] = None):
        super().__init__(parent)
        self.setWindowTitle("Add a preprocessing step")
        self.setMinimumWidth(720)
        self.chosen_step: Optional[str] = None
        already = already or set()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(T.S5, T.S4, T.S5, T.S4)
        lay.setSpacing(T.S3)

        head = QLabel("Preprocessing")
        head.setObjectName("Display")
        lay.addWidget(head)
        sub = QLabel("Applied to every image as the version is written. "
                     "Your source images are never modified.")
        sub.setObjectName("Body")
        sub.setWordWrap(True)
        lay.addWidget(sub)
        lay.addWidget(hrule())

        grid = QGridLayout()
        grid.setSpacing(T.S3)
        for i, (key, title, detail, icon_name) in enumerate(AVAILABLE):
            used = key in already
            card = StepCard(key, title,
                            "already added" if used else detail,
                            icon_name, disabled=used)
            card.chosen.connect(self._pick)
            grid.addWidget(card, i // 3, i % 3)
        lay.addLayout(grid)

        lay.addSpacing(T.S2)
        note = QLabel("NOT AVAILABLE HERE")
        note.setObjectName("SectionLabel")
        lay.addWidget(note)

        row = QHBoxLayout()
        row.setSpacing(T.S2)
        for title, where in ELSEWHERE:
            pill = QLabel(f"{title} — {where}")
            pill.setStyleSheet(
                f"background:{T.INK_850};color:{T.TX_4};border:1px solid {T.LINE};"
                f"border-radius:12px;padding:3px 10px;font-size:{T.FS_SMALL}px;")
            row.addWidget(pill)
        row.addStretch()
        lay.addLayout(row)

        lay.addWidget(Banner(
            "Cropping, sampling and class remapping across a whole dataset live on "
            "the <b>Tools</b> page, where they preview before they run.",
            "info", "sliders"))

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _pick(self, key: str):
        self.chosen_step = key
        self.accept()
