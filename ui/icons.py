"""
ui/icons.py
A small stroked icon set, drawn as SVG and rendered to QIcon at the colour and
size asked for. Replaces the emoji that used to stand in for icons: emoji pick
up whatever font the system falls back to, render at inconsistent weights, and
read as placeholder art.

    btn.setIcon(icon("trash", T.DANGER_TEXT))

All glyphs are 16x16, 1.4 stroke, round caps and joins, so they sit together.
"""
from __future__ import annotations
from typing import Dict

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from ui.theme import T

# Path data only; the wrapper supplies size, stroke and colour.
PATHS: Dict[str, str] = {
    "upload":   '<path d="M8 12V3M8 3 4.8 6.2M8 3l3.2 3.2"/>'
                '<path d="M2.5 10.5v1.8A1.7 1.7 0 0 0 4.2 14h7.6a1.7 1.7 0 0 0 1.7-1.7v-1.8"/>',
    "grid":     '<rect x="2.2" y="2.2" width="4.9" height="4.9" rx="1"/>'
                '<rect x="8.9" y="2.2" width="4.9" height="4.9" rx="1"/>'
                '<rect x="2.2" y="8.9" width="4.9" height="4.9" rx="1"/>'
                '<rect x="8.9" y="8.9" width="4.9" height="4.9" rx="1"/>',
    "pen":      '<path d="m11.3 2.4 2.3 2.3-8 8-3 .7.7-3 8-8Z"/><path d="m9.8 3.9 2.3 2.3"/>',
    "scan":     '<circle cx="7.2" cy="7.2" r="4.3"/><path d="m10.4 10.4 3 3"/>',
    "pulse":    '<path d="M1.6 8h3l1.6-4.4 2.6 8.8L10.9 8h3.5"/>',
    "sliders":  '<path d="M2.5 4.5h4M9.5 4.5h4M2.5 11.5h2M7.5 11.5h6"/>'
                '<circle cx="8" cy="4.5" r="1.5"/><circle cx="6" cy="11.5" r="1.5"/>',
    "box":      '<path d="M8 1.8 14 5v6l-6 3.2L2 11V5l6-3.2Z"/>'
                '<path d="M2 5l6 3.2L14 5M8 8.2v6"/>',
    "tag":      '<path d="M2.4 7.3V2.6h4.7l6.4 6.4-4.7 4.7L2.4 7.3Z"/><circle cx="5" cy="5" r="1"/>',
    "trash":    '<path d="M2.8 4.2h10.4M6.4 4.2V2.8h3.2v1.4"/>'
                '<path d="M4.2 4.2l.6 8.4a1 1 0 0 0 1 .9h4.4a1 1 0 0 0 1-.9l.6-8.4"/>',
    "undo":     '<path d="M2.6 6.6h6.6a3.6 3.6 0 0 1 0 7.2H6"/><path d="M5.2 3.4 2.4 6.6l2.8 3"/>',
    "redo":     '<path d="M13.4 6.6H6.8a3.6 3.6 0 0 0 0 7.2H10"/><path d="M10.8 3.4l2.8 3.2-2.8 3"/>',
    "check":    '<path d="m3 8.4 3.2 3.2L13 4.8"/>',
    "alert":    '<path d="M8 2.6 14.6 13H1.4L8 2.6Z"/><path d="M8 6.6v3M8 11.4v.1"/>',
    "eye":      '<path d="M1.4 8S3.8 3.6 8 3.6 14.6 8 14.6 8 12.2 12.4 8 12.4 1.4 8 1.4 8Z"/>'
                '<circle cx="8" cy="8" r="1.9"/>',
    "panel":    '<rect x="1.8" y="2.8" width="12.4" height="10.4" rx="1.4"/><path d="M6 2.8v10.4"/>',
    "play":     '<path d="M4.6 2.9 12.8 8l-8.2 5.1V2.9Z"/>',
    "plus":     '<path d="M8 3.2v9.6M3.2 8h9.6"/>',
    "minus":    '<path d="M3.2 8h9.6"/>',
    "cloud":    '<path d="M4.4 12.4A3 3 0 0 1 4.7 6.5a4 4 0 0 1 7.6.9 2.6 2.6 0 0 1-.5 5h-7.4Z"/>',
    "arrow":    '<path d="M3 8h10M9.4 4.4 13 8l-3.6 3.6"/>',
    "left":     '<path d="M10 3.4 5.4 8l4.6 4.6"/>',
    "right":    '<path d="M6 3.4 10.6 8 6 12.6"/>',
    "lock":     '<rect x="3.4" y="7" width="9.2" height="6.4" rx="1.3"/>'
                '<path d="M5.6 7V5.2a2.4 2.4 0 0 1 4.8 0V7"/>',
    "unlock":   '<rect x="3.4" y="7" width="9.2" height="6.4" rx="1.3"/>'
                '<path d="M5.6 7V5.2a2.4 2.4 0 0 1 4.5-.7"/>',
    "folder":   '<path d="M1.8 12.4V3.6h4l1.4 1.8h7v7a1 1 0 0 1-1 1h-10.4a1 1 0 0 1-1-1Z"/>',
    "copy":     '<rect x="5.4" y="5.4" width="8.2" height="8.2" rx="1.3"/>'
                '<path d="M10.6 5.4V3.7a1.3 1.3 0 0 0-1.3-1.3H3.7a1.3 1.3 0 0 0-1.3 1.3v5.6a1.3 1.3 0 0 0 1.3 1.3h1.7"/>',
    "search":   '<circle cx="7.2" cy="7.2" r="4.3"/><path d="m10.4 10.4 3 3"/>',
    "settings": '<circle cx="8" cy="8" r="2.1"/>'
                '<path d="M8 1.6v1.8M8 12.6v1.8M14.4 8h-1.8M3.4 8H1.6'
                'M12.5 3.5l-1.3 1.3M4.8 11.2l-1.3 1.3M12.5 12.5l-1.3-1.3M4.8 4.8 3.5 3.5"/>',
    "zoom":     '<circle cx="7.2" cy="7.2" r="4.3"/><path d="m10.4 10.4 3 3M5.4 7.2h3.6M7.2 5.4v3.6"/>',
    "fit":      '<path d="M5.6 2.4H2.4v3.2M10.4 2.4h3.2v3.2M13.6 10.4v3.2h-3.2M2.4 10.4v3.2h3.2"/>',
    "brain":    '<path d="M6.2 2.6a2.2 2.2 0 0 0-2.2 2.2 2 2 0 0 0-1 3.5 2.1 2.1 0 0 0 1.2 3.6'
                'A2.1 2.1 0 0 0 8 13.4V4.8a2.2 2.2 0 0 0-1.8-2.2Z"/>'
                '<path d="M9.8 2.6A2.2 2.2 0 0 1 12 4.8a2 2 0 0 1 1 3.5 2.1 2.1 0 0 1-1.2 3.6'
                'A2.1 2.1 0 0 1 8 13.4"/>',
    "layers":   '<path d="M8 1.9 14.4 5 8 8.1 1.6 5 8 1.9Z"/><path d="m1.6 8 6.4 3.1L14.4 8"/>'
                '<path d="m1.6 11 6.4 3.1L14.4 11"/>',
}

_cache: Dict[tuple, QIcon] = {}


def icon(name: str, color: str = T.TX_2, size: int = 16, stroke: float = 1.4) -> QIcon:
    """Return a QIcon for `name`, stroked in `color`. Results are cached."""
    key = (name, color, size, stroke)
    if key in _cache:
        return _cache[key]

    body = PATHS.get(name)
    if body is None:
        _cache[key] = QIcon()
        return _cache[key]

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" '
        f'width="{size}" height="{size}" fill="none" stroke="{color}" '
        f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">'
        f'{body}</svg>'
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()

    result = QIcon(pix)
    _cache[key] = result
    return result


def swatch(color: str, size: int = 11, radius: int = 3) -> QIcon:
    """A rounded colour chip, used wherever a class is named."""
    key = ("__swatch", color, size, radius)
    if key in _cache:
        return _cache[key]
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
        f'width="{size}" height="{size}">'
        f'<rect x="0" y="0" width="{size}" height="{size}" rx="{radius}" fill="{color}"/></svg>'
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    result = QIcon(pix)
    _cache[key] = result
    return result


def dot(color: str, size: int = 8) -> QIcon:
    return swatch(color, size, size // 2)


ICON_SIZE = QSize(16, 16)
ICON_SIZE_SM = QSize(14, 14)
