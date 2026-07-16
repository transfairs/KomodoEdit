"""Icon factory built on Komodo's real IcoMoon icon font.

Two icon sources, both reused as-is from the legacy skin tree (nothing
copied into qtedit/, same "reuse assets in place" pattern as
main_window.py's APP_ICON_PATH):

- src/chrome/komodo/skin/global/icons/fonts/icomoon.ttf (234 glyphs,
  actively maintained -- see variables.less for the name->codepoint table)
  for regular menu/toolbar icons. The older 111-PNG "classic" iconset under
  skin/images/*.png was checked and rejected: 16x16 only (no HiDPI),
  several files it references no longer exist, smaller/older vocabulary.
  Icon-font glyphs, in contrast, scale to any size and are painted in the
  current palette color rather than being baked-color PNGs.
- src/chrome/komodo/skin/images/toolbox/*.svg for toolbox item-type icons
  (snippet/command/...) that have no equivalent font glyph -- Qt loads SVG
  natively via QIcon(path), no rendering code needed for those.
"""
import os
import re

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QFont,
    QFontDatabase,
    QGuiApplication,
    QIcon,
    QPainter,
    QPalette,
    QPixmap,
)

KOMODO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SKIN_ICONS_DIR = os.path.join(KOMODO_ROOT, "src", "chrome", "komodo", "skin", "global", "icons")
FONT_PATH = os.path.join(_SKIN_ICONS_DIR, "fonts", "icomoon.ttf")
VARIABLES_PATH = os.path.join(_SKIN_ICONS_DIR, "variables.less")
TOOLBOX_SVG_DIR = os.path.join(
    KOMODO_ROOT, "src", "chrome", "komodo", "skin", "images", "toolbox"
)

_NAME_RE = re.compile(r'@icon-([\w-]+):\s*"\\([0-9a-fA-F]+)"')

_font_family = None  # None until _ensure_font() runs; "" if loading failed
_codepoints = None  # name -> str, lazily parsed from variables.less
_icon_cache = {}  # (name, size, color) -> QIcon


def _ensure_font():
    global _font_family
    if _font_family is not None:
        return _font_family
    _font_family = ""
    if os.path.isfile(FONT_PATH):
        font_id = QFontDatabase.addApplicationFont(FONT_PATH)
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            _font_family = families[0]
    return _font_family


def _ensure_codepoints():
    global _codepoints
    if _codepoints is not None:
        return _codepoints
    _codepoints = {}
    try:
        with open(VARIABLES_PATH, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return _codepoints
    for name, hex_code in _NAME_RE.findall(content):
        _codepoints[name] = chr(int(hex_code, 16))
    return _codepoints


def icon(name, size=16, color=None):
    """A QIcon rendering the named IcoMoon glyph (see variables.less for
    the full list of 234 names). Returns a null QIcon if the font or the
    glyph name can't be resolved -- callers can still setIcon() with it
    safely (Qt just shows no icon)."""
    family = _ensure_font()
    codepoint = _ensure_codepoints().get(name)
    if not family or codepoint is None:
        return QIcon()

    if color is None:
        color = QGuiApplication.palette().color(QPalette.ColorRole.ButtonText)
    cache_key = (name, size, color.name())
    cached = _icon_cache.get(cache_key)
    if cached is not None:
        return cached

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    font = QFont(family)
    font.setPixelSize(int(size * 0.85))
    painter.setFont(font)
    painter.setPen(color)
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, codepoint)
    painter.end()

    result = QIcon(pixmap)
    _icon_cache[cache_key] = result
    return result


def svg_icon(filename):
    """A QIcon loaded directly from src/chrome/komodo/skin/images/toolbox/
    (Qt's SVG icon engine handles scaling on its own, no glyph rendering
    needed here)."""
    path = os.path.join(TOOLBOX_SVG_DIR, filename)
    return QIcon(path) if os.path.isfile(path) else QIcon()
