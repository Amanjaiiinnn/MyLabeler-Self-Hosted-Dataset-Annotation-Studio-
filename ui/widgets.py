"""
ui/widgets.py
Shared components. Everything here reads from ui.theme — no widget in the app
should carry its own hex codes any more.
"""
from __future__ import annotations
from typing import Iterable, List, Optional

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QProgressBar, QPushButton, QSpinBox, QVBoxLayout, QWidget,
    QButtonGroup, QSizePolicy,
)

from ui.theme import T, mono_font
from ui.icons import icon, swatch, ICON_SIZE, ICON_SIZE_SM

# Re-exported so older imports keep resolving.
AMBER = T.WARN
AMBER_TEXT = T.WARN
MUTED = T.TX_3
BG_CARD = T.INK_850
BORDER = T.LINE


# ────────────────────────────────────────────────────────────── buttons ──

def _mk(text: str, variant: str = "", size: str = "", icon_name: str = "",
        icon_color: str = "", tooltip: str = "") -> QPushButton:
    b = QPushButton(f"  {text}" if (icon_name and text) else text)
    if variant:
        b.setProperty("variant", variant)
    if size:
        b.setProperty("size", size)
    if icon_name:
        b.setIcon(icon(icon_name, icon_color or T.TX_2))
        b.setIconSize(ICON_SIZE_SM if size == "sm" else ICON_SIZE)
    b.setCursor(Qt.PointingHandCursor)
    if tooltip:
        b.setToolTip(tooltip)
    return b


def primary_button(text: str, tooltip: str = "", icon_name: str = "", size: str = "") -> QPushButton:
    return _mk(text, "primary", size, icon_name, T.ON_ACCENT, tooltip)


def button(text: str, tooltip: str = "", icon_name: str = "", size: str = "") -> QPushButton:
    return _mk(text, "", size, icon_name, T.TX_2, tooltip)


def ghost_button(text: str, tooltip: str = "", icon_name: str = "", size: str = "") -> QPushButton:
    return _mk(text, "quiet", size, icon_name, T.TX_3, tooltip)


def danger_button(text: str, tooltip: str = "", icon_name: str = "", size: str = "") -> QPushButton:
    return _mk(text, "danger", size, icon_name, T.DANGER_TEXT, tooltip)


def chip(text: str, count: Optional[int] = None, color: str = "") -> QPushButton:
    b = QPushButton(f"{text}  {count:,}" if count is not None else text)
    b.setProperty("variant", "chip")
    b.setCheckable(True)
    b.setCursor(Qt.PointingHandCursor)
    if color:
        b.setIcon(swatch(color, 9))
        b.setIconSize(QSize(9, 9))
    return b


class Segment(QWidget):
    """A row of mutually exclusive buttons in a single recessed track."""
    changed = Signal(int)

    def __init__(self, options: Iterable[str], selected: int = 0, parent=None):
        super().__init__(parent)
        self.setObjectName("Segment")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.buttons: List[QPushButton] = []
        for i, label in enumerate(options):
            b = QPushButton(label)
            b.setProperty("variant", "segment")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setChecked(i == selected)
            self._group.addButton(b, i)
            self.buttons.append(b)
            lay.addWidget(b)
        self._group.idClicked.connect(self.changed.emit)

    def current_index(self) -> int:
        return self._group.checkedId()

    def set_current_index(self, i: int):
        if 0 <= i < len(self.buttons):
            self.buttons[i].setChecked(True)


# ─────────────────────────────────────────────────────────────── inputs ──

def line_edit(placeholder: str = "", text: str = "", width: int = 0) -> QLineEdit:
    e = QLineEdit(text)
    e.setPlaceholderText(placeholder)
    if width:
        e.setFixedWidth(width)
    return e


def spin(lo: int, hi: int, value: int, suffix: str = "", width: int = 0) -> QSpinBox:
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setValue(value)
    if suffix:
        s.setSuffix(suffix)
    if width:
        s.setFixedWidth(width)
    s.setFont(mono_font(T.FS_CONTROL))
    return s


def combo(items=None, width: int = 0) -> QComboBox:
    c = QComboBox()
    if items:
        c.addItems(items)
    if width:
        c.setFixedWidth(width)
    return c


def check(text: str, checked: bool = False) -> QCheckBox:
    c = QCheckBox(text)
    c.setChecked(checked)
    c.setCursor(Qt.PointingHandCursor)
    return c


def label(text: str, role: str = "Body", tone: str = "") -> QLabel:
    l = QLabel(text)
    l.setObjectName(role)
    if tone:
        l.setProperty("tone", tone)
    return l


def mono_label(text: str, size: int = T.FS_SMALL, color: str = "") -> QLabel:
    l = QLabel(text)
    l.setFont(mono_font(size))
    l.setStyleSheet(f"color:{color or T.TX_2};background:transparent;")
    return l


def vrule() -> QFrame:
    f = QFrame()
    f.setObjectName("VDivider")
    f.setFixedWidth(1)
    f.setFixedHeight(20)
    return f


def hrule() -> QFrame:
    f = QFrame()
    f.setObjectName("Divider")
    f.setFixedHeight(1)
    return f


def kbd(keys: str) -> QLabel:
    """A keycap. Shortcuts are printed on the screen where you press them."""
    l = QLabel(keys)
    l.setFont(mono_font(T.FS_MICRO))
    l.setAlignment(Qt.AlignCenter)
    l.setStyleSheet(
        f"background:{T.INK_700};color:{T.TX_2};border:1px solid {T.LINE_2};"
        f"border-bottom-width:2px;border-radius:4px;padding:2px 5px;")
    return l


# ───────────────────────────────────────────────────────────── surfaces ──

class Toolbar(QWidget):
    """
    A page's own action bar. Replaces the single global header: each page shows
    the actions that belong to it, and nothing else.
    """

    def __init__(self, title: str = "", subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Toolbar")
        self.setFixedHeight(T.TOOLBAR_H)
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(T.S4, 0, T.S4, 0)
        self.row.setSpacing(T.S2)

        if title:
            self.title_lbl = QLabel(title)
            self.title_lbl.setObjectName("Title")
            self.row.addWidget(self.title_lbl)
        else:
            self.title_lbl = None

        self.subtitle_lbl = QLabel(subtitle)
        self.subtitle_lbl.setObjectName("Caption")
        self.row.addWidget(self.subtitle_lbl)
        self.row.addStretch()

    def set_subtitle(self, text: str):
        self.subtitle_lbl.setText(text)

    def add(self, *widgets):
        for w in widgets:
            self.row.addWidget(w)
        return widgets[-1] if widgets else None

    def add_left(self, *widgets):
        """Insert before the stretch, right after the title."""
        idx = 2 if self.title_lbl else 1
        for w in widgets:
            self.row.insertWidget(idx, w)
            idx += 1


class StatusBar(QWidget):
    """Thin footer: what state the dataset is in, in mono."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusBar")
        self.setFixedHeight(26)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(T.S4, 0, T.S4, 0)
        lay.setSpacing(T.S4)
        self._left = mono_label("", T.FS_SMALL, T.TX_3)
        self._right = mono_label("", T.FS_SMALL, T.TX_3)
        lay.addWidget(self._left)
        lay.addStretch()
        lay.addWidget(self._right)

    def set_left(self, text: str, tone: str = ""):
        self._left.setText(text)
        self._left.setStyleSheet(f"color:{tone or T.TX_3};background:transparent;")

    def set_right(self, text: str):
        self._right.setText(text)


class Card(QFrame):
    """A titled panel. Add content to `.body`."""

    def __init__(self, title: str = "", subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(T.S4, T.S3, T.S4, T.S4)
        outer.setSpacing(T.S3)

        if title or subtitle:
            head = QHBoxLayout()
            head.setSpacing(T.S3)
            if title:
                t = QLabel(title)
                t.setStyleSheet(
                    f"font-size:{T.FS_BODY + 1}px;font-weight:600;color:{T.TX_1};")
                head.addWidget(t)
            head.addStretch()
            if subtitle:
                s = QLabel(subtitle)
                s.setObjectName("Muted")
                s.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                head.addWidget(s)
            outer.addLayout(head)
            outer.addWidget(hrule())

        self.body = QVBoxLayout()
        self.body.setSpacing(T.S2)
        outer.addLayout(self.body)


class StatTile(QWidget):
    """Caption above a big number. Used only where the figure is the point."""

    def __init__(self, caption: str, value: str = "0", sub: str = "", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(T.S4, T.S3, T.S4, T.S3)
        lay.setSpacing(1)
        cap = QLabel(caption.upper())
        cap.setObjectName("SectionLabel")
        self.value_lbl = QLabel(value)
        self.value_lbl.setFont(mono_font(22, QFont.DemiBold))
        self.value_lbl.setStyleSheet(f"color:{T.TX_1};background:transparent;")
        self.sub_lbl = QLabel(sub)
        self.sub_lbl.setObjectName("Muted")
        lay.addWidget(cap)
        lay.addWidget(self.value_lbl)
        lay.addWidget(self.sub_lbl)

    def set_value(self, value, tone: str = ""):
        self.value_lbl.setText(f"{value:,}" if isinstance(value, int) else str(value))
        self.value_lbl.setStyleSheet(f"color:{tone or T.TX_1};background:transparent;")

    def set_sub(self, text: str, tone: str = ""):
        self.sub_lbl.setText(text)
        self.sub_lbl.setStyleSheet(
            f"color:{tone or T.TX_3};font-size:{T.FS_CONTROL}px;background:transparent;")


class StatStrip(QFrame):
    """A hairline-separated row of StatTiles."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._lay = lay
        self.tiles: List[StatTile] = []

    def add_tile(self, caption: str, value: str = "0", sub: str = "") -> StatTile:
        if self.tiles:
            sep = QFrame()
            sep.setObjectName("VDivider")
            sep.setFixedWidth(1)
            self._lay.addWidget(sep)
        tile = StatTile(caption, value, sub)
        self.tiles.append(tile)
        self._lay.addWidget(tile, stretch=1)
        return tile


class Banner(QWidget):
    """An inline explanation. tone: warn | danger | ok | info."""

    def __init__(self, text: str, tone: str = "warn", icon_name: str = "alert", parent=None):
        super().__init__(parent)
        bg, fg, line = {
            "warn":   (T.WARN_WASH, T.WARN_TEXT, T.WARN),
            "danger": (T.DANGER_WASH, T.DANGER_TEXT, T.DANGER),
            "ok":     (T.OK_WASH, "#7FD98C", T.OK),
            "info":   (T.ACCENT_WASH, "#BFD6FF", T.ACCENT),
        }.get(tone, (T.WARN_WASH, T.WARN_TEXT, T.WARN))
        self.setObjectName("Banner")
        self.setStyleSheet(
            f"QWidget#Banner{{background:{bg};border:1px solid {line};"
            f"border-radius:{T.R_SM}px;}}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(T.S3, T.S2 + 2, T.S3, T.S2 + 2)
        lay.setSpacing(T.S2 + 2)
        ic = QLabel()
        ic.setPixmap(icon(icon_name, line, 15).pixmap(15, 15))
        ic.setAlignment(Qt.AlignTop)
        ic.setStyleSheet("background:transparent;border:none;")
        lay.addWidget(ic)
        self.text_lbl = QLabel(text)
        self.text_lbl.setWordWrap(True)
        self.text_lbl.setTextFormat(Qt.RichText)
        self.text_lbl.setStyleSheet(
            f"color:{fg};font-size:{T.FS_CONTROL}px;background:transparent;border:none;")
        lay.addWidget(self.text_lbl, stretch=1)

    def set_text(self, text: str):
        self.text_lbl.setText(text)


class LogPane(QPlainTextEdit):
    """Dry-run previews and operation output, in the same mono as label files."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(mono_font(T.FS_SMALL))
        self.setLineWrapMode(QPlainTextEdit.NoWrap)

    def show_lines(self, lines, limit: int = 400):
        lines = list(lines)
        text = "\n".join(lines[:limit])
        if len(lines) > limit:
            text += f"\n… and {len(lines) - limit:,} more"
        self.setPlainText(text or "(nothing to show)")


class Meter(QWidget):
    """A single horizontal bar, coloured by the class it represents."""

    def __init__(self, color: str, fraction: float = 0.0, parent=None):
        super().__init__(parent)
        self.setFixedHeight(7)
        self._color = color
        self._fraction = max(0.0, min(1.0, fraction))
        self._apply()

    def set_fraction(self, f: float):
        self._fraction = max(0.0, min(1.0, f))
        self.update()

    def _apply(self):
        self.setStyleSheet(f"background:{T.INK_750};border-radius:4px;")

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QColor, QBrush
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(T.INK_750)))
        p.drawRoundedRect(self.rect(), 3.5, 3.5)
        if self._fraction > 0:
            w = max(4, int(self.width() * self._fraction))
            p.setBrush(QBrush(QColor(self._color)))
            p.drawRoundedRect(0, 0, w, self.height(), 3.5, 3.5)
        p.end()


def progress_bar() -> QProgressBar:
    p = QProgressBar()
    p.setTextVisible(True)
    p.setFixedHeight(18)
    return p


# ───────────────────────────────────────────────── dataset target picker ──

class DatasetPicker(QWidget):
    """
    Choose what a tool runs on: the open project, or any folder on disk.
    Sits in a page's toolbar rather than in a global header.
    """
    sourceChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from core.dataset_source import DatasetSource
        self._DatasetSource = DatasetSource
        self.pm = None
        self._external = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(T.S2)

        self.target_combo = combo(["Current project"], width=200)
        self.target_combo.currentIndexChanged.connect(lambda _: self.sourceChanged.emit())
        lay.addWidget(self.target_combo)

        self.browse_btn = ghost_button(
            "Folder…", "Run these tools on any YOLO dataset folder — train/val/test, "
                       "images/labels, or a flat folder", "folder", "sm")
        self.browse_btn.clicked.connect(self._browse)
        lay.addWidget(self.browse_btn)

        self.split_combo = combo(["All splits"], width=118)
        self.split_combo.currentIndexChanged.connect(lambda _: self.sourceChanged.emit())
        lay.addWidget(self.split_combo)

        self.info_lbl = mono_label("", T.FS_SMALL, T.TX_3)
        lay.addWidget(self.info_lbl)

    def set_project(self, pm):
        self.pm = pm
        self.refresh()

    def _browse(self):
        from PySide6.QtWidgets import QFileDialog
        from core.config import settings
        start = settings().get("last_dataset_dir") or ""
        path = QFileDialog.getExistingDirectory(self, "Choose a dataset folder", start)
        if not path:
            return
        settings().set("last_dataset_dir", path)
        src = self._DatasetSource(path)
        if not src.is_valid:
            self.info_lbl.setText("no images found there")
            self.info_lbl.setStyleSheet(f"color:{T.WARN};background:transparent;")
            return
        self._external = src
        self.target_combo.blockSignals(True)
        if self.target_combo.count() > 1:
            self.target_combo.removeItem(1)
        self.target_combo.addItem(src.label)
        self.target_combo.setCurrentIndex(1)
        self.target_combo.blockSignals(False)
        self.refresh()
        self.sourceChanged.emit()

    def current_source(self):
        if self.target_combo.currentIndex() == 1 and self._external:
            self._external.refresh()
            return self._external
        if self.pm:
            return self._DatasetSource(self.pm.root, label=self.pm.root.name)
        return None

    def current_splits(self):
        src = self.current_source()
        if not src:
            return None
        idx = self.split_combo.currentIndex()
        if idx <= 0:
            return None
        return [self.split_combo.itemData(idx)]

    def refresh(self):
        src = self.current_source()
        self.split_combo.blockSignals(True)
        self.split_combo.clear()
        self.split_combo.addItem("All splits")
        if src and src.is_valid:
            for s in src.splits():
                if s:
                    self.split_combo.addItem(src.split_label(s), userData=s)
            self.split_combo.setEnabled(self.split_combo.count() > 1)
            self.info_lbl.setText(f"{src.layout} · {len(src.pairs()):,} images")
            self.info_lbl.setStyleSheet(f"color:{T.TX_3};background:transparent;")
        else:
            self.split_combo.setEnabled(False)
            self.info_lbl.setText("no dataset")
        self.split_combo.blockSignals(False)


def page_title(title: str, subtitle: str = "") -> QWidget:
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(3)
    t = QLabel(title)
    t.setObjectName("Display")
    lay.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setObjectName("Body")
        s.setWordWrap(True)
        lay.addWidget(s)
    return box


def styled(w):
    return w


INPUT_STYLE = ""
PRIMARY_BTN = ""
GHOST_BTN = ""
DANGER_BTN = ""
