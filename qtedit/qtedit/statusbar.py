"""Komodo's editor statusbar (views-editor.p.xml's <statusbar>), in classic
statusbar mode (ui.classic.statusbar): below the editor, above the find
frame.

Panels, left to right, as in the XBL binding:
- statusbar-message-panel: the breadcrumb bar (modules/breadcrumbs), which
  temporary messages replace while shown
- statusbar-pos-info: "Pos: N" (dev builds) or the selection size, then
  "Ln: L Col: C" (statusbar.p.js _updateSelectionInformation/_updateLineCol)
- statusbar-encoding: encoding menu button
- statusbar-language: language menu button
"""
import os

from PySide6.QtCore import QByteArray, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractButton,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QStatusBar,
    QToolButton,
    QWidget,
)

from qtedit import icons
from qtedit.random_color import random_color
from qtedit.skin.css import komodo_stylesheet, load_colors

KOMODO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FOLDER_ICON_PATH = os.path.join(KOMODO_ROOT, "src", "images", "icons", "folder_closed.svg")
FILEICONS_DIR = os.path.join(KOMODO_ROOT, "src", "images", "fileicons")

# Menus list at most this many directory entries, like a breadcrumb menu
# that stays usable on huge folders.
MAX_MENU_ENTRIES = 200


def _tinted_svg(path, size, color):
    """Komodo serves skin SVGs through koicon://...?scheme-color=icons,
    i.e. recolored to the interface's icon color; do the same."""
    pixmap = QIcon(path).pixmap(QSize(size, size))
    if pixmap.isNull():
        return QIcon()
    tinted = QPixmap(pixmap.size())
    tinted.fill(Qt.GlobalColor.transparent)
    painter = QPainter(tinted)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), color)
    painter.end()
    return QIcon(tinted)


# prefs.p.xml fileicons_presets: language -> colour for generated icons.
FILEICON_PRESET_COLORS = {
    "text": "#A1A1A1", "unknown": "#A1A1A1", "php": "#A075B2", "ruby": "#EB594C",
    "javascript": "#37A63A", "node.js": "#4B8850", "html": "#F2A935", "html5": "#F25D5A",
    "python": "#424B9C", "python3": "#296A9C", "css": "#5C8AB9", "less": "#362397",
}
FILEICON_TEMPLATE_SIZE = 14  # sdk/icons.js: size defaults to 14, scale = size / 14
_file_icon_cache = {}


def file_icon(language_name):
    """sdk/icons.js fileicon handler: the language's own SVG where Komodo
    ships one, else template.svg filled with the language's preset colour
    or, failing that, randomColor({luminosity: 'dark'}, language).

    'dark' is the file-URI branch (tabs, breadcrumbs). Language-URI icons
    (statusbar language menu) ask for 'light', but Komodo caches the PNG
    as language + ext + size, so whichever comes first wins; that is the
    file tab, and the screenshot shows the dark colour in both places."""
    language = language_name or "Text"  # a buffer without a language
    cached = _file_icon_cache.get(language)
    if cached is not None:
        return cached
    path = os.path.join(FILEICONS_DIR, f"{language.lower()}.svg")
    if os.path.isfile(path):
        icon = QIcon(path)
    else:
        color = FILEICON_PRESET_COLORS.get(language.lower()) or random_color(language, luminosity="dark")
        with open(os.path.join(FILEICONS_DIR, "template.svg"), encoding="utf-8") as f:
            svg = (f.read().replace("{{size}}", str(FILEICON_TEMPLATE_SIZE))
                   .replace("{{scale}}", "1").replace("{{color}}", color))
        pixmap = QPixmap(FILEICON_TEMPLATE_SIZE, FILEICON_TEMPLATE_SIZE)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(painter)
        painter.end()
        icon = QIcon(pixmap)
    _file_icon_cache[language] = icon
    return icon


class StatusbarMenuButton(QToolButton):
    """A statusbar toolbarbutton type="menu" in its statusbarpanel, drawn
    as Gecko lays it out: panel padding (toolkit default 0 4px), button
    padding, icon + 4px margin-right, the 0.6-opacity label, then the
    skin's `dropmarker:before` glyph (white, 14px) 6px after the label, or
    at the right edge when the panel's min-width is wider than that."""

    PANEL_PADDING = 4
    # Room for the dropmarker after the label (measured against Komodo
    # 12.10: 7px from the label's ink to the glyph's 4px of ink).
    MARKER_SPACE = 6
    ICON_GAP = 4  # .toolbarbutton-icon margin-right

    def __init__(self, parent=None):
        super().__init__(parent)
        css = komodo_stylesheet()
        self._marker = icons.glyph(icons.css_glyph(css.value("dropmarker:before", "content")), 16,
                                   QColor(css.value("dropmarker:before", "color")),
                                   int(css.value("dropmarker", "font-size", "14px").rstrip("px")))
        self._padding = int(css.value('[anonid="breadcrumbBar"] .breadcrumb .toolbarbutton-text',
                                      "padding", "2px").rstrip("px"))
        self._menu = None
        self.clicked.connect(self._popup)

    def _content_width(self):
        width = self.fontMetrics().horizontalAdvance(self.text())
        if not self.icon().isNull():
            width += self.iconSize().width() + self.ICON_GAP
        return width

    def sizeHint(self):
        width = 2 * (self.PANEL_PADDING + self._padding) + self._content_width() + self.MARKER_SPACE
        return QSize(width, super().sizeHint().height())

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, event):
        painter = QPainter(self)
        box = self.rect().adjusted(self.PANEL_PADDING, 0, -self.PANEL_PADDING, 0)
        if self.underMouse():
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.palette().button())
            painter.drawRoundedRect(box, self._padding, self._padding)
        x = box.left() + self._padding
        if not self.icon().isNull():
            size = self.iconSize()
            self.icon().paint(painter, QRect(x, (self.height() - size.height()) // 2,
                                             size.width(), size.height()))
            x += size.width() + self.ICON_GAP
        painter.setPen(self.palette().buttonText().color())
        painter.drawText(QRect(x, 0, box.right() - x, self.height()), Qt.AlignmentFlag.AlignVCenter,
                         self.text())
        # The glyph's ink is columns 6-9 of its 16px box; Komodo's ends 2px
        # before the button padding.
        marker_x = box.right() + 1 - self._padding - self.MARKER_SPACE - 2
        self._marker.paint(painter, QRect(marker_x, (self.height() - 16) // 2, 16, 16))
        painter.end()

    # QToolButton.setMenu() makes sizeHint reserve room for Qt's own menu
    # indicator, so the menu is kept and shown here instead.
    def setMenu(self, menu):
        self._menu = menu

    def menu(self):
        return self._menu

    def setPopupMode(self, _mode):
        pass

    def _popup(self):
        """position="before_end": above the button, right edges aligned."""
        if self._menu is None:
            return
        hint = self._menu.sizeHint()
        self._menu.exec(self.mapToGlobal(QPoint(self.width() - hint.width(), -hint.height())))


class Crumb(QAbstractButton):
    """One `.breadcrumb` toolbarbutton, painted with the breadcrumbs skin's
    geometry: icon, icon margin, text box (padding + rounded hover
    background), then the arrow glyph with its own margins."""

    def __init__(self, label, icon, icon_gap, style, parent=None):
        super().__init__(parent)
        self.setText(label)
        self._icon = icon
        self._icon_gap = icon_gap
        self._style = style
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def _text_width(self):
        return self.fontMetrics().horizontalAdvance(self.text())

    def sizeHint(self):
        st = self._style
        arrow_w = QFontMetrics(st["arrow_font"]).horizontalAdvance(st["arrow"])
        width = (st["margin_left"] + 14 + self._icon_gap + 2 * st["text_pad"]
                 + self._text_width() + st["arrow_margin"] * 2 + arrow_w)
        return QSize(width, self.fontMetrics().height() + 2 * st["text_pad"])

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, _event):
        st = self._style
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.height()
        x = st["margin_left"]
        self._icon.paint(painter, QRect(x, (h - 14) // 2, 14, 14))
        x += 14 + self._icon_gap
        text_w = self._text_width() + 2 * st["text_pad"]
        text_h = self.fontMetrics().height() + 2 * st["text_pad"]
        text_rect = QRect(x, (h - text_h) // 2, text_w, text_h)
        if self.underMouse():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(st["hover_bg"])
            painter.drawRoundedRect(text_rect, st["radius"], st["radius"])
        painter.setPen(st["hover_fg"] if self.underMouse() else st["fg"])
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.text())
        x += text_w + st["arrow_margin"]
        painter.setFont(st["arrow_font"])
        painter.setPen(st["arrow_color"])
        painter.drawText(QRect(x, 0, self.width() - x, h), Qt.AlignmentFlag.AlignVCenter, st["arrow"])
        painter.end()


def _css_px(value, default=0):
    try:
        return int(float(str(value).replace("px", "").split()[0]))
    except (ValueError, IndexError):
        return default


class Breadcrumbs(QWidget):
    """modules/breadcrumbs: one crumb per path segment of the current file.
    Clicking a folder crumb lists that folder; picking a file opens it.
    Leading crumbs that don't fit are hidden, as Komodo's
    `.breadcrumb.overflown { visibility: collapse }` does."""

    open_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("breadcrumbBar")
        # Never force the statusbar wider; overflow is handled by hiding.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        css = komodo_stylesheet()
        colors = load_colors()
        folder_rule = css.rule('[anonid="breadcrumbBar"] .breadcrumb.folder .breadcrumb-icon')
        icon_color = QColor(colors["icons"])
        icon_color.setAlphaF(float(folder_rule.get("opacity", 1)))
        self._folder_icon = _tinted_svg(FOLDER_ICON_PATH, 14, icon_color)
        self._folder_gap = _css_px(folder_rule.get("margin-right"), 2)
        self._file_gap = _css_px(
            css.value('[anonid="breadcrumbBar"] .breadcrumb .toolbarbutton-icon', "margin-right"), 4
        )
        text_rule = css.rule('[anonid="breadcrumbBar"] .breadcrumb .toolbarbutton-text')
        hover_rule = css.rule('[anonid="breadcrumbBar"] .breadcrumb:hover .toolbarbutton-text')
        arrow_rule = css.rule('[anonid="breadcrumbBar"] .breadcrumb .breadcrumb-arrow')
        fg = QColor(colors["foreground"])
        fg.setAlphaF(float(css.value("#komodo_main statusbar .toolbarbutton-text", "opacity", 1)))
        arrow_font = QFont(icons.font_family())
        arrow_font.setPixelSize(_css_px(arrow_rule.get("font-size"), 14))
        arrow_margins = [_css_px(v) for v in arrow_rule.get("margin", "0 2px").split()]
        self._style = {
            "fg": fg,
            "hover_fg": QColor(hover_rule["color"]),
            "hover_bg": QColor(hover_rule["background"]),
            "radius": _css_px(text_rule.get("border-radius"), 2),
            "text_pad": _css_px(text_rule.get("padding"), 2),
            "arrow": icons.css_glyph(css.value(".breadcrumb-arrow:before", "content")),
            "arrow_font": arrow_font,
            "arrow_color": QColor(arrow_rule["color"]),
            "arrow_margin": arrow_margins[1] if len(arrow_margins) > 1 else arrow_margins[0],
            "margin_left": 0,
        }
        self._first_margin = _css_px(
            css.value('[anonid="breadcrumbBar"] .breadcrumb.first-child', "margin-left"), 6
        )
        self._crumbs = []
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(
            _css_px(css.value('[anonid="breadcrumbBar"]', "margin", "0 0 0 4px").split()[-1]), 0, 0, 0
        )
        self._layout.setSpacing(0)
        self._layout.addStretch(1)

    def set_path(self, path, language_name=None):
        for crumb in self._crumbs:
            self._layout.removeWidget(crumb)
            crumb.deleteLater()
        self._crumbs = []
        if not path:
            return
        path = os.path.abspath(path)
        parts = []
        head = path
        while True:
            head, tail = os.path.split(head)
            if not tail:
                parts.append(("(root)", head))
                break
            parts.append((tail, os.path.join(head, tail)))
        parts.reverse()
        for i, (label, crumb_path) in enumerate(parts):
            is_file = i == len(parts) - 1
            style = dict(self._style, margin_left=self._first_margin if i == 0 else 0)
            crumb = Crumb(
                label,
                file_icon(language_name) if is_file else self._folder_icon,
                self._file_gap if is_file else self._folder_gap,
                style,
            )
            menu_dir = os.path.dirname(crumb_path) if is_file else crumb_path
            crumb.clicked.connect(lambda _checked=False, b=crumb, d=menu_dir: self._show_menu(b, d))
            self._layout.insertWidget(len(self._crumbs), crumb)
            self._crumbs.append(crumb)
        self._update_overflow()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_overflow()

    def _update_overflow(self):
        available = self.width() - self._layout.contentsMargins().left()
        used = 0
        # Keep the file and as many trailing folders as fit.
        for crumb in reversed(self._crumbs):
            used += crumb.sizeHint().width()
            crumb.setVisible(used <= available or crumb is self._crumbs[-1])

    def _show_menu(self, button, directory):
        menu = QMenu(self)
        self._fill_menu(menu, directory)
        menu.exec(button.mapToGlobal(button.rect().topLeft()))

    def _fill_menu(self, menu, directory):
        try:
            names = sorted(os.listdir(directory), key=str.lower)
        except OSError:
            names = []
        dirs = [n for n in names if os.path.isdir(os.path.join(directory, n))]
        files = [n for n in names if n not in dirs]
        for name in (dirs + files)[:MAX_MENU_ENTRIES]:
            full = os.path.join(directory, name)
            if name in dirs:
                sub = menu.addMenu(self._folder_icon, name)
                sub.setProperty("folderItem", True)
                sub.aboutToShow.connect(
                    lambda m=sub, d=full: m.isEmpty() and self._fill_menu(m, d)
                )
            else:
                action = menu.addAction(name)
                action.triggered.connect(lambda _c=False, p=full: self.open_requested.emit(p))
        if menu.isEmpty():
            menu.addAction("(empty)").setEnabled(False)


class EditorStatusBar(QStatusBar):
    open_requested = Signal(str)

    # Measured against Komodo 12.10: the last panel ends 3px before the edge.
    RIGHT_MARGIN = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContentsMargins(0, 0, self.RIGHT_MARGIN, 0)
        self.setSizeGripEnabled(False)
        self._editor = None

        self.breadcrumbs = Breadcrumbs()
        self.breadcrumbs.open_requested.connect(self.open_requested)
        self.addWidget(self.breadcrumbs, 1)

        self._selection_label = QLabel()
        self._selection_label.setObjectName("statusbar-selection")
        self._line_col_label = QLabel()
        self._line_col_label.setObjectName("statusbar-line-col")
        pos_info = QWidget()
        pos_info.setObjectName("statusbar-pos-info")
        pos_layout = QHBoxLayout(pos_info)
        pos_layout.setContentsMargins(0, 0, 0, 0)
        pos_layout.setSpacing(0)
        pos_layout.addStretch(1)
        pos_layout.addWidget(self._selection_label)
        pos_layout.addWidget(self._line_col_label)
        min_width = komodo_stylesheet().value(
            '#komodo_main statusbar statusbarpanel[anonid="statusbar-pos-info"]', "min-width"
        )
        if min_width:
            pos_info.setMinimumWidth(int(min_width.rstrip("px")))
        self.addPermanentWidget(pos_info)

        # Both panels: min-width 5rem (views-editor.p.xml).
        # Gecko keeps the fractional rem (11pt = 14.67px) and floors: 73px.
        rem = self.font().pointSizeF() * self.logicalDpiY() / 72
        panel_min_width = int(5 * rem + 1e-6)
        self._encoding_button = StatusbarMenuButton()
        # Measured against Komodo: the 5rem include the panel padding.
        self._encoding_button.setMinimumWidth(panel_min_width)
        self._encoding_button.setObjectName("statusbar-encoding-label")
        self._encoding_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._encoding_button.setMenu(QMenu(self._encoding_button))
        self._encoding_button.menu().addAction("UTF-8").setEnabled(False)

        self._language_button = StatusbarMenuButton()
        self._language_button.setObjectName("statusbar-language-menu")
        self._language_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._language_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._language_button.setMenu(QMenu(self._language_button))
        self.language_menu_filler = None
        self._language_button.menu().aboutToShow.connect(self._fill_language_menu)
        # XUL statusbarpanels sit edge to edge, but QStatusBar spaces its
        # items (and resets any spacing set on its layout), so the two
        # menu panels share one container.
        menus = QWidget()
        menus_layout = QHBoxLayout(menus)
        menus_layout.setContentsMargins(0, 0, 0, 0)
        menus_layout.setSpacing(0)
        menus_layout.addWidget(self._encoding_button)
        menus_layout.addWidget(self._language_button)
        self.addPermanentWidget(menus)

    def _fill_language_menu(self):
        """statusbar-filetype-menu: the same list as View > View as Language."""
        menu = self._language_button.menu()
        menu.clear()
        if self.language_menu_filler is not None:
            self.language_menu_filler(menu)

    def set_editor(self, editor):
        if self._editor is not None:
            try:
                self._editor.updateUi.disconnect(self._update_position)
            except (RuntimeError, TypeError):
                pass
        self._editor = editor
        if editor is None:
            self.breadcrumbs.set_path(None)
            return
        editor.updateUi.connect(self._update_position)
        self.refresh()

    def refresh(self):
        """Re-read file path and language of the current editor (after
        open/save-as/language change)."""
        editor = self._editor
        if editor is None:
            return
        language = editor.language_name()
        self.breadcrumbs.set_path(editor.filepath, language)
        self._encoding_button.setText("UTF-8")
        self._language_button.setText(language or "Text")
        self._language_button.setIcon(file_icon(language))
        self._update_position()

    def _update_position(self, *_args):
        editor = self._editor
        if editor is None:
            return
        pos = editor.currentPos()
        start, end = editor.selectionStart(), editor.selectionEnd()
        if start != end:
            chars = editor.countCharacters(start, end)
            text = f"Sel: {chars} ch"
            if chars != end - start:
                text += f", {end - start} by"
            last_line = editor.lineFromPosition(editor.positionBefore(end))
            text += f", {abs(last_line - editor.lineFromPosition(start)) + 1} ln"
        else:
            # Komodo shows the raw position only in dev builds; 12.10-devel
            # is what qtedit is compared against, so keep it.
            text = f"Pos: {pos}"
        self._selection_label.setText(text)
        line = editor.lineFromPosition(pos) + 1
        column = editor.column(pos) + 1
        self._line_col_label.setText(f"Ln: {line} Col: {column}")
