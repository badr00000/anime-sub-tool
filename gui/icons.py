"""
Line icons: one set, 24-unit grid, stroke 1.5, drawn in the colour of the text
they sit next to. Rendered from inline SVG so the app ships no icon font.
"""

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_PATHS = {
    "folder": '<path d="M3.5 7.5A1.5 1.5 0 0 1 5 6h4l2 2h8a1.5 1.5 0 0 1 1.5 1.5v8A1.5 1.5 0 0 1 19 19H5'
              'a1.5 1.5 0 0 1-1.5-1.5z"/>',
    "layers": '<path d="M4 9h11v10H4z"/><path d="M8.5 9V5H20v10h-5"/>',
    "captions": '<rect x="3.5" y="5" width="17" height="14" rx="2"/><path d="M7 15h5M14.5 15H17M7 12h3"/>',
    "sliders": '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
    "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8h.01"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "chevron_left": '<path d="M14.5 6l-6 6 6 6"/>',
    "chevron_right": '<path d="M9.5 6l6 6-6 6"/>',
    "chevron_down": '<path d="M6 9.5l6 6 6-6"/>',
    "download": '<path d="M12 4v11M7.5 10.5L12 15l4.5-4.5M5 19.5h14"/>',
    "alert": '<path d="M12 4.5L3 19.5h18z"/><path d="M12 10v4M12 16.8h.01"/>',
    "x": '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
    "play": '<path d="M8 5.5v13l10.5-6.5z"/>',
    "pause": '<path d="M9 6v12M15 6v12"/>',
    "reset": '<path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3"/><path d="M4.5 4.5v4h4"/>',
    "dot": '<circle cx="12" cy="12" r="3.5" fill="currentColor"/>',
}


def _svg(name: str, color: str) -> bytes:
    body = _PATHS[name].replace("currentColor", color)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{body}</svg>').encode()


@lru_cache(maxsize=256)
def pixmap(name: str, color: str, size: int = 16, ratio: float = 2.0) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(_svg(name, color)))
    px = QPixmap(int(size * ratio), int(size * ratio))
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    renderer.render(painter, QRectF(0, 0, px.width(), px.height()))
    painter.end()
    px.setDevicePixelRatio(ratio)
    return px


def icon(name: str, color: str, size: int = 16, active_color: str | None = None) -> QIcon:
    """An icon in `color`; `active_color` is used for the checked/selected state."""
    ic = QIcon(pixmap(name, color, size))
    if active_color:
        ic.addPixmap(pixmap(name, active_color, size), QIcon.Mode.Normal, QIcon.State.On)
        ic.addPixmap(pixmap(name, active_color, size), QIcon.Mode.Active, QIcon.State.Off)
    return ic
