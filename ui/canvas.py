"""
ui/canvas.py
QGraphicsView-based canvas for drawing, selecting, resizing, locking, and deleting
YOLO annotations on top of an image. Supports undo/redo, duplicate, context menu,
zoom controls, and pixel-level precision.

An annotation is either an axis-aligned box or an OBB / polygon. Polygons are
stored as fractions of their own bounding rect, so moving or resizing the rect
carries the rotated shape along with it instead of flattening it.
"""
from __future__ import annotations
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QRectF, Signal, QPointF
from PySide6.QtGui import QPen, QBrush, QColor, QFont, QPixmap, QAction, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsPixmapItem,
    QGraphicsSimpleTextItem, QMenu,
)

from core.annotation import BBox

HANDLE_SIZE = 9
MAX_UNDO = 50
_ORDER = [0]      # monotonically increasing id for stable box ordering
MIN_SCALE = 0.02
MAX_SCALE = 60.0


class BoxItem(QGraphicsRectItem):
    """A movable / resizable annotation with class badge, lock and optional OBB."""

    def __init__(self, rect: QRectF, class_id: int, class_name: str,
                 color: str, confidence: Optional[float] = None,
                 poly_frac: Optional[List[Tuple[float, float]]] = None):
        super().__init__(rect)
        self.class_id = class_id
        self.class_name = class_name
        self.confidence = confidence
        self.locked = False
        _ORDER[0] += 1
        self.order = _ORDER[0]
        # polygon vertices as fractions (0-1) of this item's own rect
        self.poly_frac: Optional[List[Tuple[float, float]]] = poly_frac
        self._color = QColor(color)
        self._resizing_handle: Optional[str] = None

        self.setFlags(
            QGraphicsRectItem.ItemIsMovable |
            QGraphicsRectItem.ItemIsSelectable |
            QGraphicsRectItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self._apply_pen_brush()

        self.label_bg = QGraphicsRectItem(self)
        self.label_bg.setPen(Qt.NoPen)

        self.label_item = QGraphicsSimpleTextItem(self)
        self.label_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self.label_item.setBrush(QBrush(Qt.white))
        self._update_label()

    # ------------------------------------------------------------- polygon
    @property
    def is_polygon(self) -> bool:
        return bool(self.poly_frac) and len(self.poly_frac) >= 4

    def polygon_points(self) -> List[QPointF]:
        """Polygon vertices in item-local coordinates."""
        if not self.is_polygon:
            return []
        r = self.rect()
        return [QPointF(r.left() + fx * r.width(), r.top() + fy * r.height())
                for fx, fy in self.poly_frac]

    @staticmethod
    def poly_frac_from_points(points: List[Tuple[float, float]],
                              rect: QRectF) -> List[Tuple[float, float]]:
        w = rect.width() or 1.0
        h = rect.height() or 1.0
        return [((px - rect.left()) / w, (py - rect.top()) / h) for px, py in points]

    # -------------------------------------------------------------- styling
    def _apply_pen_brush(self):
        self.setPen(QPen(self._color, 2))
        fill = QColor(self._color)
        fill.setAlpha(0 if self.is_polygon else 25)
        self.setBrush(QBrush(fill))

    def _update_label(self):
        txt = self.class_name
        if self.confidence is not None:
            txt += f" {self.confidence:.2f}"
        if self.is_polygon:
            txt = "◇ " + txt
        if self.locked:
            txt = "🔒 " + txt
        self.label_item.setText(txt)
        self._position_label()

    def _position_label(self):
        r = self.rect()
        self.label_item.setPos(r.left() + 4, r.top() - 19)
        lb = self.label_item.boundingRect()
        bg_color = QColor(self._color)
        bg_color.setAlpha(220)
        self.label_bg.setBrush(QBrush(bg_color))
        self.label_bg.setRect(QRectF(r.left() + 1, r.top() - 21, lb.width() + 6, lb.height() + 4))

    def set_class(self, class_id: int, class_name: str, color: str):
        self.class_id = class_id
        self.class_name = class_name
        self._color = QColor(color)
        self._apply_pen_brush()
        self._update_label()

    def set_locked(self, locked: bool):
        self.locked = locked
        self.setFlag(QGraphicsRectItem.ItemIsMovable, not locked)
        self._update_label()
        self.update()

    # -------------------------------------------------------------- painting
    def paint(self, painter, option, widget=None):
        option.state &= ~option.state.__class__(0x00000008)   # drop Qt's selection box

        if self.is_polygon:
            poly = QPolygonF(self.polygon_points())
            fill = QColor(self._color)
            fill.setAlpha(40)
            painter.setBrush(QBrush(fill))
            painter.setPen(QPen(self._color, 2))
            painter.drawPolygon(poly)
            # faint bounding rect so the drag/resize target stays discoverable
            hint = QColor(self._color)
            hint.setAlpha(90)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(hint, 1, Qt.DotLine))
            painter.drawRect(self.rect())
        else:
            super().paint(painter, option, widget)

        if self.isSelected():
            painter.setPen(QPen(self._color, 2, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.rect().adjusted(-1, -1, 1, 1))
            if not self.locked:
                painter.setBrush(QBrush(Qt.white))
                painter.setPen(QPen(self._color, 1))
                for hx, hy in self._handle_points():
                    painter.drawRect(QRectF(
                        hx - HANDLE_SIZE / 2, hy - HANDLE_SIZE / 2,
                        HANDLE_SIZE, HANDLE_SIZE))

    def _handle_points(self):
        r = self.rect()
        return [
            (r.left(), r.top()), (r.right(), r.top()),
            (r.left(), r.bottom()), (r.right(), r.bottom()),
            (r.center().x(), r.top()), (r.center().x(), r.bottom()),
            (r.left(), r.center().y()), (r.right(), r.center().y()),
        ]

    def _handle_at(self, pos: QPointF) -> Optional[str]:
        if self.locked:
            return None
        names = ["tl", "tr", "bl", "br", "t", "b", "l", "r"]
        for name, (hx, hy) in zip(names, self._handle_points()):
            if abs(pos.x() - hx) <= HANDLE_SIZE and abs(pos.y() - hy) <= HANDLE_SIZE:
                return name
        return None

    # ---------------------------------------------------------------- mouse
    def hoverMoveEvent(self, event):
        if self.locked:
            self.setCursor(Qt.ForbiddenCursor)
            return
        handle = self._handle_at(event.pos()) if self.isSelected() else None
        cursor_map = {
            "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
            "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
            "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
            "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
        }
        self.setCursor(cursor_map.get(
            handle, Qt.SizeAllCursor if self.isSelected() else Qt.ArrowCursor))
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if self.locked:
            super().mousePressEvent(event)
            return
        if self.isSelected():
            self._resizing_handle = self._handle_at(event.pos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.locked:
            return
        if self._resizing_handle:
            r = self.rect()
            p = event.pos()
            if "l" in self._resizing_handle:
                r.setLeft(min(p.x(), r.right() - 5))
            if "r" in self._resizing_handle:
                r.setRight(max(p.x(), r.left() + 5))
            if "t" in self._resizing_handle:
                r.setTop(min(p.y(), r.bottom() - 5))
            if "b" in self._resizing_handle:
                r.setBottom(max(p.y(), r.top() + 5))
            self.setRect(r)          # poly_frac is relative, so the OBB follows
            self._position_label()
            self.update()
        else:
            super().mouseMoveEvent(event)
            self._position_label()

    def mouseReleaseEvent(self, event):
        self._resizing_handle = None
        super().mouseReleaseEvent(event)

    def scene_rect(self) -> QRectF:
        return self.rect().translated(self.pos())


class Canvas(QGraphicsView):
    boxAdded = Signal(object)
    boxRemoved = Signal(object)
    boxSelected = Signal(object)
    boxesChanged = Signal()
    undoAvailable = Signal(bool)
    redoAvailable = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene_ = QGraphicsScene(self)
        self.setScene(self.scene_)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setMouseTracking(True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)

        self.pixmap_item: Optional[QGraphicsPixmapItem] = None
        self.img_w = 0
        self.img_h = 0

        self.draw_mode = False
        self._drawing = False
        self._draw_start: Optional[QPointF] = None
        self._temp_rect_item: Optional[QGraphicsRectItem] = None
        self._user_zoomed = False        # stop resizeEvent from stealing the zoom

        self.current_class_id = 0
        self.current_class_name = "class0"
        self.current_class_color = "#a78bfa"
        self.class_lookup: dict = {}

        self._undo_stack: list = []
        self._redo_stack: list = []
        self._snap_before: Optional[list] = None
        self._mouse_moved = False

        self.setBackgroundBrush(QBrush(QColor("#0b0b14")))
        self.scene_.selectionChanged.connect(self._on_selection_changed)

    # ---------------------------------------------------------------- image
    def load_image(self, path: str):
        self.scene_.clear()
        self.pixmap_item = None
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._user_zoomed = False
        self.undoAvailable.emit(False)
        self.redoAvailable.emit(False)
        pix = QPixmap(path)
        if pix.isNull():
            self.img_w = self.img_h = 0
            self.scene_.setSceneRect(0, 0, 1, 1)
            return False
        self.img_w, self.img_h = pix.width(), pix.height()
        self.pixmap_item = self.scene_.addPixmap(pix)
        self.scene_.setSceneRect(0, 0, self.img_w, self.img_h)
        self.fit_to_view()
        return True

    def fit_to_view(self):
        if self.pixmap_item:
            self.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
            self._user_zoomed = False

    def zoom_to_100(self):
        self.resetTransform()
        if self.pixmap_item:
            self.centerOn(self.pixmap_item)
        self._user_zoomed = True

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # only re-fit while the user is still at the default zoom
        if not self._user_zoomed:
            self.fit_to_view()

    # -------------------------------------------------------------- classes
    def set_classes(self, classes: List[Tuple[int, str, str]]):
        self.class_lookup = {cid: (name, color) for cid, name, color in classes}
        for item in self._box_items():
            if True:
                name, color = self.class_lookup.get(
                    item.class_id, (item.class_name, "#a78bfa"))
                item.set_class(item.class_id, name, color)

    def set_current_class(self, class_id: int):
        if class_id in self.class_lookup:
            self.current_class_id = class_id
            self.current_class_name, self.current_class_color = self.class_lookup[class_id]

    # ---------------------------------------------------------------- boxes
    def _box_items(self) -> List[BoxItem]:
        """Every BoxItem in the order it was added, not in z-order."""
        items = [i for i in self.scene_.items() if isinstance(i, BoxItem)]
        return sorted(items, key=lambda i: i.order)

    def clear_boxes(self):
        for item in list(self.scene_.items()):
            if isinstance(item, BoxItem):
                self.scene_.removeItem(item)

    def add_box_item(self, rect: QRectF, class_id: int,
                     confidence: Optional[float] = None,
                     locked: bool = False,
                     poly_frac: Optional[List[Tuple[float, float]]] = None) -> BoxItem:
        name, color = self.class_lookup.get(class_id, (f"class{class_id}", "#a78bfa"))
        item = BoxItem(rect, class_id, name, color, confidence, poly_frac)
        if locked:
            item.set_locked(True)
        self.scene_.addItem(item)
        return item

    def load_boxes(self, boxes: List[BBox]):
        self.clear_boxes()
        if not self.img_w or not self.img_h:
            return
        for b in boxes:
            x1, y1, x2, y2 = b.to_pixels(self.img_w, self.img_h)
            rect = QRectF(x1, y1, x2 - x1, y2 - y1)
            poly_frac = None
            if b.is_polygon:
                pts = b.polygon_pixels(self.img_w, self.img_h)
                poly_frac = BoxItem.poly_frac_from_points(pts, rect)
            self.add_box_item(rect, b.class_id, b.confidence, poly_frac=poly_frac)

    def get_boxes(self) -> List[BBox]:
        if not self.img_w or not self.img_h:
            return []
        boxes = []
        for item in self._box_items():
            r = item.scene_rect()
            if item.is_polygon:
                pos = item.pos()
                flat = []
                for p in item.polygon_points():
                    flat.append(min(1.0, max(0.0, (p.x() + pos.x()) / self.img_w)))
                    flat.append(min(1.0, max(0.0, (p.y() + pos.y()) / self.img_h)))
                boxes.append(BBox.from_polygon(item.class_id, flat))
            else:
                boxes.append(BBox.from_pixels(
                    item.class_id, r.left(), r.top(), r.right(), r.bottom(),
                    self.img_w, self.img_h, confidence=None))
        return boxes

    def selected_box(self) -> Optional[BoxItem]:
        sel = self.scene_.selectedItems()
        return sel[0] if sel and isinstance(sel[0], BoxItem) else None

    def delete_selected(self):
        item = self.selected_box()
        if item:
            self._push_undo()
            self.scene_.removeItem(item)
            self.boxRemoved.emit(item)
            self.boxesChanged.emit()

    def duplicate_selected(self):
        item = self.selected_box()
        if not item:
            return
        self._push_undo()
        r = item.scene_rect()
        new_rect = r.translated(15, 15).intersected(QRectF(0, 0, self.img_w, self.img_h))
        if new_rect.width() > 4 and new_rect.height() > 4:
            new_item = self.add_box_item(
                new_rect, item.class_id, item.confidence, item.locked,
                list(item.poly_frac) if item.poly_frac else None)
            self.scene_.clearSelection()
            new_item.setSelected(True)
            self.boxAdded.emit(new_item)
            self.boxesChanged.emit()

    def set_selected_class(self, class_id: int):
        item = self.selected_box()
        if item:
            self._push_undo()
            name, color = self.class_lookup.get(class_id, (f"class{class_id}", "#a78bfa"))
            item.set_class(class_id, name, color)
            self.boxesChanged.emit()
            self.boxSelected.emit(item)

    def set_selected_geometry(self, x: int, y: int, w: int, h: int):
        item = self.selected_box()
        if item:
            self._push_undo()
            item.setPos(x, y)
            item.setRect(QRectF(0, 0, w, h))
            item._position_label()
            item.update()
            self.boxesChanged.emit()

    def toggle_lock_selected(self):
        item = self.selected_box()
        if item:
            item.set_locked(not item.locked)
            self.boxesChanged.emit()
            self.boxSelected.emit(item)

    def set_lock_selected(self, locked: bool):
        item = self.selected_box()
        if item:
            item.set_locked(locked)
            self.boxesChanged.emit()
            self.boxSelected.emit(item)

    # ------------------------------------------------------------ undo/redo
    def _snapshot(self) -> list:
        snap = []
        for item in self._box_items():
            if True:
                r = item.scene_rect()
                snap.append({
                    "class_id": item.class_id,
                    "class_name": item.class_name,
                    "x": r.x(), "y": r.y(), "w": r.width(), "h": r.height(),
                    "confidence": item.confidence,
                    "locked": item.locked,
                    "poly": list(item.poly_frac) if item.poly_frac else None,
                    "order": item.order,
                })
        return snap

    def _restore_snapshot(self, snap: list):
        self.clear_boxes()
        for d in snap:
            item = self.add_box_item(
                QRectF(d["x"], d["y"], d["w"], d["h"]),
                d["class_id"], d["confidence"], d["locked"], d.get("poly"))
            if d.get("order") is not None:
                item.order = d["order"]
        self.boxesChanged.emit()

    def _push_undo(self):
        self._undo_stack.append(self._snapshot())
        if len(self._undo_stack) > MAX_UNDO:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self.undoAvailable.emit(True)
        self.redoAvailable.emit(False)

    def undo(self):
        if not self._undo_stack:
            return
        self._redo_stack.append(self._snapshot())
        self._restore_snapshot(self._undo_stack.pop())
        self.undoAvailable.emit(bool(self._undo_stack))
        self.redoAvailable.emit(True)

    def redo(self):
        if not self._redo_stack:
            return
        self._undo_stack.append(self._snapshot())
        self._restore_snapshot(self._redo_stack.pop())
        self.undoAvailable.emit(True)
        self.redoAvailable.emit(bool(self._redo_stack))

    # ------------------------------------------------------------ draw mode
    def set_draw_mode(self, on: bool):
        self.draw_mode = on
        self.setCursor(Qt.CrossCursor if on else Qt.ArrowCursor)
        self.setDragMode(QGraphicsView.NoDrag)

    def _on_selection_changed(self):
        self.boxSelected.emit(self.selected_box())

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self._show_context_menu(event)
            return
        if self.draw_mode and self.pixmap_item and event.button() == Qt.LeftButton:
            self._drawing = True
            self._draw_start = self.mapToScene(event.pos())
            self._temp_rect_item = self.scene_.addRect(
                QRectF(self._draw_start, self._draw_start),
                QPen(QColor(self.current_class_color), 2, Qt.DashLine))
            return
        sp = self.mapToScene(event.pos())
        if any(isinstance(i, BoxItem) for i in self.scene_.items(sp)):
            self._snap_before = self._snapshot()
            self._mouse_moved = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drawing and self._temp_rect_item:
            cur = self.mapToScene(event.pos())
            self._temp_rect_item.setRect(QRectF(self._draw_start, cur).normalized())
            return
        if self._snap_before is not None and (event.buttons() & Qt.LeftButton):
            self._mouse_moved = True
        super().mouseMoveEvent(event)
        if self._snap_before is not None:
            for item in self.scene_.selectedItems():
                if isinstance(item, BoxItem):
                    item._position_label()

    def mouseReleaseEvent(self, event):
        if self._drawing and event.button() == Qt.LeftButton:
            self._drawing = False
            rect = self._temp_rect_item.rect() if self._temp_rect_item else QRectF()
            if self._temp_rect_item:
                self.scene_.removeItem(self._temp_rect_item)
                self._temp_rect_item = None
            rect = rect.intersected(QRectF(0, 0, self.img_w, self.img_h))
            if rect.width() > 4 and rect.height() > 4:
                self._push_undo()
                item = self.add_box_item(rect, self.current_class_id)
                self.scene_.clearSelection()
                item.setSelected(True)
                self.boxAdded.emit(item)
                self.boxesChanged.emit()
            return
        if self._snap_before is not None and self._mouse_moved:
            if self._snapshot() != self._snap_before:
                self._undo_stack.append(self._snap_before)
                if len(self._undo_stack) > MAX_UNDO:
                    self._undo_stack.pop(0)
                self._redo_stack.clear()
                self.undoAvailable.emit(True)
                self.redoAvailable.emit(False)
                self.boxesChanged.emit()
        self._snap_before = None
        self._mouse_moved = False
        super().mouseReleaseEvent(event)

    def _show_context_menu(self, event):
        sp = self.mapToScene(event.pos())
        boxes = [i for i in self.scene_.items(sp) if isinstance(i, BoxItem)]
        if not boxes:
            return
        box = boxes[0]
        self.scene_.clearSelection()
        box.setSelected(True)

        menu = QMenu(self)
        cls_menu = menu.addMenu("Change Class")
        for cid in sorted(self.class_lookup.keys()):
            name, _color = self.class_lookup[cid]
            act = QAction(f"[{cid}] {name}", self)
            act.triggered.connect(lambda chk=False, c=cid: self.set_selected_class(c))
            cls_menu.addAction(act)

        menu.addSeparator()
        dup_act = QAction("⧉ Duplicate (Ctrl+D)", self)
        dup_act.triggered.connect(self.duplicate_selected)
        menu.addAction(dup_act)

        lock_act = QAction("Unlock" if box.locked else "🔒 Lock", self)
        lock_act.triggered.connect(self.toggle_lock_selected)
        menu.addAction(lock_act)

        menu.addSeparator()
        del_act = QAction("Delete (Del)", self)
        del_act.triggered.connect(self.delete_selected)
        menu.addAction(del_act)

        menu.exec(event.globalPosition().toPoint())

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()
        if key in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected()
        elif key == Qt.Key_L and not mods:
            self.toggle_lock_selected()
        elif key in (Qt.Key_Left, Qt.Key_Right):
            event.ignore()
            return
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        current = self.transform().m11()
        target = current * factor
        if target < MIN_SCALE or target > MAX_SCALE:
            return
        self.scale(factor, factor)
        self._user_zoomed = True
