"""
ui/projects_view.py — the workspace landing screen.

A grid of project cards, laid out like Roboflow's Projects page: thumbnail,
type badge, name, when it was last edited, and the image count. Clicking one
opens it; the rest of the app then works inside that project.

Everything on a card is derived from the folder itself (ProjectManager.describe)
rather than stored, so a project copied in from elsewhere still shows correctly.
"""
from __future__ import annotations
import time
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, QRectF, QSize
from PySide6.QtGui import QPixmap, QPainter, QColor, QBrush, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QScrollArea,
    QFrame, QSizePolicy, QMenu, QMessageBox,
)

from core.project import ProjectManager
from ui.theme import T, mono_font
from ui.icons import icon
from ui.widgets import (
    Toolbar, StatusBar, button, ghost_button, primary_button, danger_button,
    line_edit, combo, mono_label, vrule,
)

CARD_W, CARD_H = 336, 108
THUMB = 84


def ago(ts: float) -> str:
    """`Edited 5 days ago` — the same phrasing Roboflow uses."""
    if not ts:
        return "never edited"
    delta = max(0, time.time() - ts)
    mins = delta / 60
    if mins < 1:
        return "Edited just now"
    if mins < 60:
        n = int(mins)
        return f"Edited {n} minute{'s' if n != 1 else ''} ago"
    hours = mins / 60
    if hours < 24:
        n = int(hours)
        return f"Edited {n} hour{'s' if n != 1 else ''} ago"
    days = hours / 24
    if days < 31:
        n = int(days)
        return f"Edited {n} day{'s' if n != 1 else ''} ago"
    months = days / 30.44
    if months < 12:
        n = max(1, int(months))
        return f"Edited {n} month{'s' if n != 1 else ''} ago"
    years = days / 365.25
    n = max(1, int(years))
    return f"Edited {n} year{'s' if n != 1 else ''} ago"


class ProjectCard(QFrame):
    """One project. Double-click or single-click opens it."""
    opened = Signal(object)      # Path
    deleteRequested = Signal(object)
    renameRequested = Signal(object)

    def __init__(self, info: dict, parent=None):
        super().__init__(parent)
        self.info = info
        self.path: Path = info["path"]
        self.setObjectName("ProjectCard")
        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(Qt.PointingHandCursor)
        self._hot = False
        self._apply_style()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(T.S3, T.S3, T.S3, T.S3)
        lay.setSpacing(T.S3)

        self.thumb = QLabel()
        self.thumb.setFixedSize(THUMB, THUMB)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet(
            f"background:{T.INK_950};border-radius:{T.R_SM}px;")
        self._render_thumb()
        lay.addWidget(self.thumb)

        col = QVBoxLayout()
        col.setSpacing(4)
        col.setContentsMargins(0, 2, 0, 2)

        badge = QLabel("  Object Detection")
        badge.setFixedHeight(19)
        badge.setStyleSheet(
            f"color:{T.TX_3};font-size:{T.FS_MICRO}px;font-weight:600;"
            f"background:{T.INK_800};border:1px solid {T.LINE};"
            f"border-radius:4px;padding:0 7px;")
        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.addWidget(badge, alignment=Qt.AlignLeft)
        badge_row.addStretch()
        self.menu_btn = ghost_button("", "More", "sliders", "sm")
        self.menu_btn.setFixedWidth(26)
        self.menu_btn.clicked.connect(self._show_menu)
        badge_row.addWidget(self.menu_btn)
        col.addLayout(badge_row)

        self.name_lbl = QLabel(info["name"])
        self.name_lbl.setStyleSheet(
            f"color:{T.TX_1};font-size:{T.FS_TITLE}px;font-weight:600;")
        self.name_lbl.setToolTip(str(self.path))
        col.addWidget(self.name_lbl)

        self.edited_lbl = QLabel(ago(info["modified"]))
        self.edited_lbl.setObjectName("Muted")
        col.addWidget(self.edited_lbl)

        bits = [f"{info['images']:,} Images"]
        if info["classes"]:
            bits.append(f"{len(info['classes'])} Classes")
        if info["versions"]:
            bits.append(f"{info['versions']} Version"
                        f"{'s' if info['versions'] != 1 else ''}")
        self.meta_lbl = mono_label("  ·  ".join(bits), T.FS_SMALL, T.TX_3)
        col.addWidget(self.meta_lbl)
        col.addStretch()
        lay.addLayout(col, stretch=1)

    def _render_thumb(self):
        src = self.info.get("thumbnail")
        if src and Path(src).exists():
            pix = QPixmap(str(src))
            if not pix.isNull():
                scaled = pix.scaled(THUMB, THUMB, Qt.KeepAspectRatioByExpanding,
                                    Qt.SmoothTransformation)
                # centre-crop to a square so cards stay uniform
                x = max(0, (scaled.width() - THUMB) // 2)
                y = max(0, (scaled.height() - THUMB) // 2)
                self.thumb.setPixmap(scaled.copy(x, y, THUMB, THUMB))
                return
        placeholder = QPixmap(THUMB, THUMB)
        placeholder.fill(QColor(T.INK_800))
        p = QPainter(placeholder)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(T.TX_4), 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(26, 26, 32, 32), 4, 4)
        p.end()
        self.thumb.setPixmap(placeholder)

    def _apply_style(self):
        border = T.LINE_3 if self._hot else T.LINE
        bg = T.INK_800 if self._hot else T.INK_850
        self.setStyleSheet(
            f"QFrame#ProjectCard{{background:{bg};border:1px solid {border};"
            f"border-radius:{T.R}px;}}")

    def enterEvent(self, event):
        self._hot = True
        self._apply_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hot = False
        self._apply_style()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self.menu_btn.geometry().contains(event.pos()):
                self.opened.emit(self.path)
        super().mousePressEvent(event)

    def _show_menu(self):
        menu = QMenu(self)
        act_open = menu.addAction("Open project")
        act_rename = menu.addAction("Rename…")
        menu.addSeparator()
        act_del = menu.addAction("Delete project…")
        chosen = menu.exec(self.menu_btn.mapToGlobal(
            self.menu_btn.rect().bottomLeft()))
        if chosen == act_open:
            self.opened.emit(self.path)
        elif chosen == act_rename:
            self.renameRequested.emit(self.path)
        elif chosen == act_del:
            self.deleteRequested.emit(self.path)


class ProjectsView(QWidget):
    """Workspace landing: every project under projects/, newest first."""

    projectOpened = Signal(object)       # Path
    newProjectRequested = Signal()
    openFolderRequested = Signal()

    def __init__(self, projects_root: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.projects_root = Path(projects_root)
        self._infos: List[dict] = []
        self.cards: List[ProjectCard] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        tb = Toolbar("Workspace")
        tb.set_subtitle(str(self.projects_root))
        self.btn_open_folder = button(
            "Open folder…", "Open a dataset folder that lives somewhere else",
            "folder", "sm")
        self.btn_open_folder.clicked.connect(self.openFolderRequested)
        self.btn_new = primary_button("New Project", "Create an empty project",
                                      "plus", "sm")
        self.btn_new.clicked.connect(self.newProjectRequested)
        tb.add(self.btn_open_folder, self.btn_new)
        root.addWidget(tb)

        # ── filter row ────────────────────────────────────────
        bar = QWidget()
        bar.setObjectName("Toolbar")
        bar.setFixedHeight(T.TOOLBAR_H)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(T.S6, 0, T.S6, 0)
        bl.setSpacing(T.S2)
        self.search = line_edit("Search projects", width=250)
        self.search.textChanged.connect(self.render)
        bl.addWidget(self.search)
        sort_lbl = QLabel("Sort")
        sort_lbl.setObjectName("Muted")
        bl.addWidget(sort_lbl)
        self.sort_combo = combo(["Date edited", "Name", "Image count"], width=140)
        self.sort_combo.currentIndexChanged.connect(lambda _: self.render())
        bl.addWidget(self.sort_combo)
        bl.addStretch()
        self.count_lbl = mono_label("", T.FS_SMALL, T.TX_3)
        bl.addWidget(self.count_lbl)
        root.addWidget(bar)

        # ── grid ──────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.grid_host = QWidget()
        self.grid_host.setObjectName("Page")
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(T.S6, T.S5, T.S6, T.S5)
        self.grid.setSpacing(T.S3)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(self.grid_host)
        root.addWidget(scroll, stretch=1)

        self.status = StatusBar()
        root.addWidget(self.status)

        self.empty_lbl = QLabel()
        self.empty_lbl.setObjectName("Body")
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.empty_lbl.setWordWrap(True)
        self.empty_lbl.hide()

    # ---------------------------------------------------------------- data
    def refresh(self):
        self._infos = ProjectManager.list_projects(self.projects_root)
        self.render()

    def render(self):
        query = self.search.text().strip().lower()
        infos = [i for i in self._infos if not query or query in i["name"].lower()]

        mode = self.sort_combo.currentIndex()
        if mode == 1:
            infos.sort(key=lambda d: d["name"].lower())
        elif mode == 2:
            infos.sort(key=lambda d: d["images"], reverse=True)
        else:
            infos.sort(key=lambda d: d["modified"], reverse=True)

        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self.cards.clear()

        if not infos:
            msg = ("No projects yet.\n\nUse New Project to create one, or "
                   "Open folder… to point at a dataset that already exists."
                   if not self._infos else
                   f"No project matches “{self.search.text().strip()}”.")
            self.empty_lbl.setText(msg)
            self.empty_lbl.show()
            self.grid.addWidget(self.empty_lbl, 0, 0)
        else:
            self.empty_lbl.hide()
            cols = max(1, (self.grid_host.width() - T.S6 * 2) // (CARD_W + T.S3))
            for i, info in enumerate(infos):
                card = ProjectCard(info)
                card.opened.connect(self.projectOpened)
                card.deleteRequested.connect(self._delete_project)
                card.renameRequested.connect(self._rename_project)
                self.cards.append(card)
                self.grid.addWidget(card, i // cols, i % cols)

        total_imgs = sum(i["images"] for i in self._infos)
        self.count_lbl.setText(f"{len(infos)} of {len(self._infos)} shown")
        self.status.set_left(
            f"{len(self._infos)} project(s) · {total_imgs:,} images total")
        self.status.set_right(str(self.projects_root))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.cards:
            cols = max(1, (self.grid_host.width() - T.S6 * 2) // (CARD_W + T.S3))
            for i, card in enumerate(self.cards):
                self.grid.addWidget(card, i // cols, i % cols)

    # ------------------------------------------------------------- actions
    def _rename_project(self, path: Path):
        from PySide6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self, "Rename project", "New folder name:", text=path.name)
        new_name = new_name.strip()
        if not ok or not new_name or new_name == path.name:
            return
        target = path.parent / new_name
        if target.exists():
            QMessageBox.warning(self, "Name already used",
                                f"A folder called “{new_name}” already exists here.")
            return
        try:
            path.rename(target)
        except OSError as e:
            QMessageBox.warning(self, "Could not rename",
                                f"{e}\n\nIf the project is open, close it first.")
            return
        self.refresh()

    def _delete_project(self, path: Path):
        info = next((i for i in self._infos if i["path"] == path), None)
        n = info["images"] if info else 0
        box = QMessageBox(self)
        box.setWindowTitle("Delete project")
        box.setIcon(QMessageBox.Warning)
        box.setText(f"Delete the project “{path.name}”?")
        box.setInformativeText(
            f"This permanently removes the folder and everything in it — "
            f"{n:,} image(s), their labels, augmentations and exports.\n\n"
            f"{path}\n\nThis cannot be undone.")
        del_btn = box.addButton("Delete permanently", QMessageBox.DestructiveRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.setDefaultButton(box.buttons()[-1])
        box.exec()
        if box.clickedButton() is not del_btn:
            return
        import shutil
        try:
            shutil.rmtree(path)
        except OSError as e:
            QMessageBox.warning(self, "Could not delete",
                                f"{e}\n\nIf the project is open, close it first.")
            return
        self.refresh()
