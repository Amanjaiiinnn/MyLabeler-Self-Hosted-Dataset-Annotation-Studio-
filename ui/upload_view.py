"""
ui/upload_view.py — bringing images into a project.

One drop target, an honest statement of what will and will not import, and a
running list of what landed. The old page advertised video and .avif support
that does not exist; this one states the real formats.
"""
from __future__ import annotations
from pathlib import Path
from typing import List

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QFileDialog, QScrollArea,
    QGridLayout, QSizePolicy,
)

from core.dataset_source import IMAGE_EXTENSIONS
from ui.theme import T
from ui.icons import icon
from ui.widgets import (
    Toolbar, StatusBar, Card, Banner, button, ghost_button, primary_button,
    mono_label, hrule, line_edit,
)

FILE_FILTER = "Images (*.jpg *.jpeg *.png *.bmp *.webp *.tiff *.tif);;All files (*.*)"


class DropZone(QFrame):
    """The drop target. Its border is the only dashed edge in the app."""
    filesDropped = Signal(list)
    browseFiles = Signal()
    browseFolder = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(230)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._hot = False
        self._apply_style()

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(T.S3)

        glyph = QLabel()
        glyph.setPixmap(icon("upload", T.ACCENT, 22).pixmap(22, 22))
        glyph.setFixedSize(48, 48)
        glyph.setAlignment(Qt.AlignCenter)
        glyph.setStyleSheet(
            f"background:{T.ACCENT_WASH};border:1px solid {T.ACCENT_DIM};"
            f"border-radius:24px;")
        lay.addWidget(glyph, alignment=Qt.AlignCenter)

        headline = QLabel("Drop images or a dataset folder here")
        headline.setObjectName("Title")
        headline.setAlignment(Qt.AlignCenter)
        lay.addWidget(headline)

        sub = QLabel("Matching .txt label files are imported alongside them")
        sub.setObjectName("Muted")
        sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(sub)

        row = QHBoxLayout()
        row.setSpacing(T.S2)
        row.setAlignment(Qt.AlignCenter)
        b1 = primary_button("Choose files", icon_name="copy")
        b1.clicked.connect(self.browseFiles)
        b2 = button("Choose folder", icon_name="folder")
        b2.clicked.connect(self.browseFolder)
        row.addWidget(b1)
        row.addWidget(b2)
        lay.addLayout(row)

    def _apply_style(self):
        color = T.ACCENT if self._hot else T.LINE_2
        bg = T.ACCENT_WASH if self._hot else T.INK_850
        self.setStyleSheet(
            f"QFrame#DropZone{{background:{bg};border:2px dashed {color};"
            f"border-radius:{T.R_LG}px;}}")

    def _set_hot(self, hot: bool):
        self._hot = hot
        self._apply_style()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_hot(True)

    def dragLeaveEvent(self, event):
        self._set_hot(False)

    def dropEvent(self, event: QDropEvent):
        self._set_hot(False)
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile()]
        if paths:
            self.filesDropped.emit(paths)


class UploadView(QWidget):
    importFilesRequested = Signal(list)
    importFolderRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        tb = Toolbar("Upload")
        tb.set_subtitle("images and their labels")
        self.btn_files = ghost_button("Files…", "Pick individual images", "copy", "sm")
        self.btn_files.clicked.connect(self._browse_files)
        self.btn_folder = ghost_button("Folder…", "Import a whole dataset folder",
                                       "folder", "sm")
        self.btn_folder.clicked.connect(self._browse_folder)
        tb.add(self.btn_files, self.btn_folder)
        root.addWidget(tb)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("Page")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(T.S6, T.S5, T.S6, T.S5)
        lay.setSpacing(T.S4)

        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(T.S3)
        batch_col = QVBoxLayout()
        batch_col.setSpacing(4)
        batch_lbl = QLabel("Batch name")
        batch_lbl.setObjectName("SectionLabel")
        from datetime import datetime
        self.batch_edit = line_edit(
            "", datetime.now().strftime("Uploaded on %d/%m/%y at %I:%M %p"))
        batch_col.addWidget(batch_lbl)
        batch_col.addWidget(self.batch_edit)
        hl.addLayout(batch_col, stretch=1)
        lay.addWidget(header)

        self.drop_zone = DropZone()
        self.drop_zone.browseFiles.connect(self._browse_files)
        self.drop_zone.browseFolder.connect(self._browse_folder)
        self.drop_zone.filesDropped.connect(self._handle_dropped)
        lay.addWidget(self.drop_zone, stretch=1)

        lower = QHBoxLayout()
        lower.setSpacing(T.S4)
        lower.addWidget(self._build_formats_card(), stretch=1)
        lower.addWidget(self._build_pairing_card(), stretch=1)
        lay.addLayout(lower)

        lay.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

        self.status = StatusBar()
        self.status.set_left("nothing imported yet")
        root.addWidget(self.status)

    def _build_formats_card(self) -> Card:
        card = Card("Supported formats",
                    "Anything else in the folder is skipped, not renamed or moved")
        grid = QGridLayout()
        grid.setHorizontalSpacing(T.S6)
        grid.setVerticalSpacing(T.S2)

        exts = "  ".join(sorted(e for e in IMAGE_EXTENSIONS))
        rows = [
            ("Images", exts, T.OK),
            ("Annotations", ".txt in YOLO format — boxes and OBB/polygon", T.OK),
            ("Class names", "classes.txt, data.yaml or _darknet.labels", T.OK),
            ("Video", "not supported — extract frames first", T.TX_4),
        ]
        for r, (name, detail, tone) in enumerate(rows):
            n = QLabel(name)
            n.setStyleSheet(
                f"color:{T.TX_1 if tone != T.TX_4 else T.TX_3};"
                f"font-size:{T.FS_CONTROL}px;font-weight:600;")
            d = mono_label(detail, T.FS_SMALL, tone if tone == T.TX_4 else T.TX_2)
            grid.addWidget(n, r, 0, alignment=Qt.AlignTop)
            grid.addWidget(d, r, 1)
        grid.setColumnStretch(1, 1)
        card.body.addLayout(grid)
        return card

    def _build_pairing_card(self) -> Card:
        card = Card("How labels are matched",
                    "by filename stem, in this order")
        for i, text in enumerate([
            "the same folder as the image      photo.jpg  →  photo.txt",
            "a labels/ folder beside it        images/photo.jpg  →  labels/photo.txt",
            "a labels/ folder inside it        photo.jpg  →  labels/photo.txt",
        ], 1):
            row = QHBoxLayout()
            row.setSpacing(T.S3)
            n = mono_label(str(i), T.FS_SMALL, T.TX_4)
            n.setFixedWidth(14)
            row.addWidget(n)
            row.addWidget(mono_label(text, T.FS_SMALL, T.TX_2), stretch=1)
            card.body.addLayout(row)

        card.body.addWidget(hrule())
        card.body.addWidget(Banner(
            "Class ids found in imported labels are registered automatically, so "
            "an id the project has never seen still gets a name, a colour and a "
            "valid entry in <b>data.yaml</b>.", "info", "check"))
        return card

    # ------------------------------------------------------------- actions
    def _browse_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select images to import", "", FILE_FILTER)
        if paths:
            self.status.set_left(f"importing {len(paths)} file(s)…")
            self.importFilesRequested.emit(paths)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select a dataset folder")
        if folder:
            self.status.set_left(f"importing {Path(folder).name}…")
            self.importFolderRequested.emit(folder)

    def _handle_dropped(self, paths: List[str]):
        if not paths:
            return
        if len(paths) == 1 and Path(paths[0]).is_dir():
            self.status.set_left(f"importing {Path(paths[0]).name}…")
            self.importFolderRequested.emit(paths[0])
        else:
            self.status.set_left(f"importing {len(paths)} file(s)…")
            self.importFilesRequested.emit(paths)

    def set_project(self, pm):
        self.pm = pm
        if pm:
            self.status.set_right(f"into {pm.root.name}")
