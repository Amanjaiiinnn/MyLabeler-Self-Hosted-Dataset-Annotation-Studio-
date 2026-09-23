"""
ui/sidebar.py — the app's only chrome.

Nine destinations under three headings, a project header, and a trash footer.
Collapses to an icon rail so the canvas gets ~160px back on Annotate and Review.
Everything that used to live in a top header bar now sits either here (global:
project, model) or in each page's own toolbar (page-specific actions).
"""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QButtonGroup, QSizePolicy,
)

from ui.theme import T
from ui.icons import icon, ICON_SIZE

# (key, label, icon name)
GROUPS: List[Tuple[str, List[Tuple[str, str, str]]]] = [
    ("WORKSPACE", [
        ("projects", "All Projects", "layers"),
    ]),
    ("DATA", [
        ("upload",   "Upload",     "upload"),
        ("dataset",  "Dataset",    "grid"),
        ("annotate", "Annotate",   "pen"),
        ("review",   "Review",     "scan"),
    ]),
    ("QUALITY", [
        ("health",   "Health",     "pulse"),
        ("tools",    "Tools",      "sliders"),
    ]),
    ("OUTPUT", [
        ("versions", "Versions",   "box"),
        ("classes",  "Classes",    "tag"),
    ]),
]


class NavItem(QPushButton):
    """One destination. Shows a count, or an amber flag when it needs attention."""

    def __init__(self, key: str, label: str, icon_name: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.label_text = label
        self.icon_name = icon_name
        self.setCheckable(True)
        self.setAutoExclusive(False)
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("variant", "nav")
        self.setIconSize(ICON_SIZE)
        self.setToolTip(label)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        self._badge = QLabel("", self)
        self._badge.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._badge.hide()

        self._collapsed = False
        self._badge_text = ""
        self._badge_tone = "count"
        self._refresh_icon()
        self.setText(f"  {label}")
        self.toggled.connect(lambda _: self._refresh_icon())

    def _refresh_icon(self):
        color = T.ACCENT if self.isChecked() else T.TX_3
        self.setIcon(icon(self.icon_name, color))

    def set_badge(self, text: str, tone: str = "count"):
        """tone: 'count' (neutral) or 'warn' (amber pill)."""
        self._badge_text = text or ""
        self._badge_tone = tone
        self._layout_badge()

    def set_collapsed(self, collapsed: bool):
        self._collapsed = collapsed
        self.setText("" if collapsed else f"  {self.label_text}")
        self._layout_badge()

    def _layout_badge(self):
        if not self._badge_text:
            self._badge.hide()
            return
        if self._collapsed:
            # a dot in the corner is all that fits
            if self._badge_tone == "warn":
                self._badge.setText("")
                self._badge.setFixedSize(6, 6)
                self._badge.setStyleSheet(
                    f"background:{T.WARN};border-radius:3px;")
                self._badge.move(self.width() - 13, 7)
                self._badge.show()
            else:
                self._badge.hide()
            return

        self._badge.setText(self._badge_text)
        if self._badge_tone == "warn":
            self._badge.setStyleSheet(
                f"background:{T.WARN_WASH};color:{T.WARN};border-radius:8px;"
                f"padding:1px 7px;font-family:'{T.FONT_MONO}';"
                f"font-size:{T.FS_MICRO}px;font-weight:600;")
        else:
            self._badge.setStyleSheet(
                f"background:transparent;color:{T.TX_3};"
                f"font-family:'{T.FONT_MONO}';font-size:{T.FS_SMALL}px;")
        self._badge.adjustSize()
        self._badge.move(self.width() - self._badge.width() - 12,
                         (self.height() - self._badge.height()) // 2)
        self._badge.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_badge()


class Sidebar(QWidget):
    navigationChanged = Signal(str)
    openProjectRequested = Signal()
    newProjectRequested = Signal()
    trashRequested = Signal()
    collapsedChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Rail")
        self.setFixedWidth(T.RAIL_W)
        self._collapsed = False
        self.items: Dict[str, NavItem] = {}
        self._group_labels: List[QLabel] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, T.S3, 0, T.S3)
        root.setSpacing(0)

        root.addWidget(self._build_project_header())
        root.addSpacing(T.S2)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for title, entries in GROUPS:
            lbl = QLabel(title)
            lbl.setObjectName("GroupLabel")
            self._group_labels.append(lbl)
            root.addWidget(lbl)
            for key, label, icon_name in entries:
                item = NavItem(key, label, icon_name)
                item.clicked.connect(lambda _=False, k=key: self.navigationChanged.emit(k))
                self._group.addButton(item)
                self.items[key] = item
                holder = QWidget()
                hl = QHBoxLayout(holder)
                hl.setContentsMargins(T.S2, 0, T.S2, 0)
                hl.addWidget(item)
                root.addWidget(holder)

        root.addStretch()
        root.addWidget(self._build_footer())

        self.items["dataset"].setChecked(True)

    # ------------------------------------------------------------ header
    def _build_project_header(self) -> QWidget:
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(T.S3, 0, T.S3, 0)
        wl.setSpacing(T.S2)

        self._proj_card = QFrame()
        self._proj_card.setObjectName("Card")
        self._proj_card.setStyleSheet(
            f"QFrame#Card {{ background:{T.INK_750}; border:1px solid {T.LINE}; "
            f"border-radius:{T.R}px; }}")
        pl = QHBoxLayout(self._proj_card)
        pl.setContentsMargins(10, 9, 10, 9)
        pl.setSpacing(10)

        glyph = QLabel()
        glyph.setPixmap(icon("box", T.TX_2, 16).pixmap(16, 16))
        glyph.setFixedSize(30, 30)
        glyph.setAlignment(Qt.AlignCenter)
        glyph.setStyleSheet(
            f"background:{T.INK_650};border-radius:{T.R_SM}px;")
        pl.addWidget(glyph)

        names = QVBoxLayout()
        names.setSpacing(1)
        self._proj_name = QLabel("No project")
        self._proj_name.setStyleSheet(
            f"font-size:{T.FS_BODY}px;font-weight:600;color:{T.TX_1};")
        self._proj_meta = QLabel("object detection")
        self._proj_meta.setStyleSheet(
            f"font-family:'{T.FONT_MONO}';font-size:{T.FS_MICRO}px;color:{T.TX_3};")
        names.addWidget(self._proj_name)
        names.addWidget(self._proj_meta)
        pl.addLayout(names, stretch=1)
        self._proj_glyph = glyph
        wl.addWidget(self._proj_card)

        self._proj_btns = QWidget()
        bl = QHBoxLayout(self._proj_btns)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(T.S1)
        open_btn = QPushButton("Open")
        open_btn.setProperty("variant", "quiet")
        open_btn.setProperty("size", "sm")
        open_btn.setIcon(icon("folder", T.TX_3))
        open_btn.setToolTip("Open a project or dataset folder  (Ctrl+O)")
        open_btn.clicked.connect(self.openProjectRequested)
        new_btn = QPushButton("New")
        new_btn.setProperty("variant", "quiet")
        new_btn.setProperty("size", "sm")
        new_btn.setIcon(icon("plus", T.TX_3))
        new_btn.setToolTip("Create a new project  (Ctrl+N)")
        new_btn.clicked.connect(self.newProjectRequested)
        bl.addWidget(open_btn)
        bl.addWidget(new_btn)
        bl.addStretch()
        self._open_btn, self._new_btn = open_btn, new_btn
        wl.addWidget(self._proj_btns)
        return wrap

    # ------------------------------------------------------------ footer
    def _build_footer(self) -> QWidget:
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(T.S2, T.S2, T.S2, 0)
        wl.setSpacing(T.S1)

        rule = QFrame()
        rule.setObjectName("Divider")
        rule.setFixedHeight(1)
        wl.addWidget(rule)
        wl.addSpacing(T.S2)

        self._trash_btn = QPushButton("Trash")
        self._trash_btn.setProperty("variant", "nav")
        self._trash_btn.setIcon(icon("trash", T.TX_3))
        self._trash_btn.setIconSize(ICON_SIZE)
        self._trash_btn.setCursor(Qt.PointingHandCursor)
        self._trash_btn.setToolTip("Restore deleted files  (Ctrl+Shift+Z)")
        self._trash_btn.clicked.connect(self.trashRequested)
        wl.addWidget(self._trash_btn)

        self._collapse_btn = QPushButton("Collapse")
        self._collapse_btn.setProperty("variant", "nav")
        self._collapse_btn.setIcon(icon("panel", T.TX_3))
        self._collapse_btn.setIconSize(ICON_SIZE)
        self._collapse_btn.setCursor(Qt.PointingHandCursor)
        self._collapse_btn.clicked.connect(self.toggle_collapsed)
        wl.addWidget(self._collapse_btn)
        return wrap

    # -------------------------------------------------------------- state
    def set_project_info(self, name: str, count: int = 0):
        self._proj_name.setText(name)
        self._proj_name.setToolTip(name)
        self.items["dataset"].set_badge(f"{count:,}" if count else "")

    def set_health_badge(self, problems: int = 0):
        self.items["health"].set_badge(
            f"{problems:,}" if problems else "", "warn" if problems else "count")

    def set_badge(self, key: str, text: str, tone: str = "count"):
        if key in self.items:
            self.items[key].set_badge(text, tone)

    def set_trash_info(self, count: int = 0):
        self._trash_btn.setText("Trash" if self._collapsed else
                                (f"  Trash · {count}" if count else "  Trash"))
        self._trash_btn.setEnabled(count > 0)
        if self._collapsed:
            self._trash_btn.setText("")

    def set_active(self, key: str):
        if key in self.items:
            self.items[key].setChecked(True)

    # ---------------------------------------------------------- collapsing
    def toggle_collapsed(self):
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool):
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self.setFixedWidth(T.RAIL_W_COLLAPSED if collapsed else T.RAIL_W)
        for lbl in self._group_labels:
            lbl.setVisible(not collapsed)
        for item in self.items.values():
            item.set_collapsed(collapsed)
        self._proj_btns.setVisible(not collapsed)
        self._proj_name.setVisible(not collapsed)
        self._proj_meta.setVisible(not collapsed)
        self._proj_card.setVisible(not collapsed)
        self._trash_btn.setText("" if collapsed else "  Trash")
        self._collapse_btn.setText("" if collapsed else "  Collapse")
        self._collapse_btn.setToolTip("Expand sidebar" if collapsed else "Collapse sidebar")
        self.collapsedChanged.emit(collapsed)

    @property
    def collapsed(self) -> bool:
        return self._collapsed


# Old name, kept so nothing else has to change.
RoboflowSidebar = Sidebar
