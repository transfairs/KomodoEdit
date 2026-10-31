"""Builds qtedit's Qt stylesheet from Komodo's compiled skin CSS.

Every value below is looked up by the Komodo selector that styles the
equivalent XUL element (see css.py), never typed in by hand, so switching
the snapshot to another Komodo skin/scheme restyles qtedit the same way.
QSS has no box-shadow, so Komodo's inset-shadow underlines and focus rings
become borders of the same width and color.

Widgets opt into Komodo-specific rules via objectName, named after the XUL
element id they stand in for (e.g. "tabbed-view" for the editor tab bar).
"""
import re

from PySide6.QtGui import QColor, QFontMetrics, QPalette

from qtedit.skin.css import komodo_stylesheet, load_colors

_LENGTH_RE = re.compile(r"(-?[\d.]+)(px|rem|em)?$")
_SHADOW_RE = re.compile(r"(inset\s+)?(-?\d+)px\s+(-?\d+)px\s+(-?\d+)px\s+(-?\d+)px\s+(.+)$")


def _px(value, rem_px, default=0):
    """'1.6rem' / '32px' / '0' -> integer pixels."""
    if value is None:
        return default
    match = _LENGTH_RE.match(value.strip())
    if not match:
        return default
    number = float(match.group(1))
    if match.group(2) in ("rem", "em"):
        number *= rem_px
    return round(number)


def _box(value, rem_px):
    """CSS shorthand ('2px 6px', '0 6px', '0.2rem 4px') -> 'Tpx Rpx Bpx Lpx'."""
    parts = [_px(p, rem_px) for p in value.split()]
    while len(parts) < 4:
        parts.append(parts[len(parts) - 2] if len(parts) >= 2 else parts[0])
    return " ".join(f"{p}px" for p in parts[:4])


def _shadow(value):
    """'inset 0px -2px 0px 0px #202024' -> (spread_or_offset_px, color)."""
    match = _SHADOW_RE.match(value.strip())
    if not match:
        return 0, None
    _inset, x, y, _blur, spread, color = match.groups()
    return max(abs(int(x)), abs(int(y)), int(spread)), color.strip()


def _faded(color, opacity):
    """Komodo fades labels with `opacity`; QSS can't, so bake it into the
    text color."""
    q = QColor(color)
    return f"rgba({q.red()}, {q.green()}, {q.blue()}, {float(opacity)})"


def build_qss(rem_px, line_px):
    """line_px: height of one line of UI text, used to turn Komodo's
    min-heights into padding where QSS ignores min-height."""
    css = komodo_stylesheet()
    c = load_colors()
    rule = css.rule

    root = rule(":root")

    # Menubar: Komodo 12 draws it as a toolbar inside #toolbox_main; the
    # menus sit in a toolbaritem that carries the bar color.
    menubar_bg = rule("#komodo_main #toolbox_main toolbar toolbaritem")["background"]
    menu = rule("menu")
    menubar_pad_v = max(0, (_px(menu["min-height"], rem_px) - line_px) // 2)
    popup_box = rule("menupopup > .popup-internal-box")
    popup_item = rule("menuitem")
    popup_active = rule("menupopup menuitem[_moz-menuactive=\"true\"]")
    popup_separator = rule("menupopup menuseparator")

    # Editor tabs (#tabbed-view > tabs) and pane tabs (ko-pane tabs) are
    # both non-embedded <tabs>, so the generic :not(.embedded) > tabs rules
    # style both; Qt tab bars opt in with the koTabs property.
    tabs = rule(":not(.embedded) > tabs")
    tab = rule("tab")
    tab_strip = rule(":not(.embedded) > tabs tab")
    # Unselected tabs reserve the underline's space with a transparent
    # border, so selecting one doesn't shift the label.
    tab_unselected = rule(":not(.embedded) > tabs tab:not([selected])")
    tab_selected = rule(":not(.embedded) > tabs tab[selected]")
    tab_hover = rule(":not(.embedded) > tabs tab:not([selected]):hover")
    tab_shadow_width, tab_shadow_color = _shadow(tabs["box-shadow"])
    file_tab = rule('tab[type="file-tab"]')

    icon_tab = rule('#komodo_main ko-pane[type="icons"] tab')

    # Classic statusbar mode (ui.classic.statusbar) overrides the base rule.
    statusbar = {
        **rule("#komodo_main statusbar"),
        **rule('#komodo_main[classic-statusbar="true"] statusbar'),
    }
    statusbar_label = rule("#komodo_main statusbar statusbarpanel > label")
    statusbar_text = _faded(root["color"], statusbar_label["opacity"])
    crumb_text = rule('[anonid="breadcrumbBar"] .breadcrumb .toolbarbutton-text')
    crumb_hover = rule('[anonid="breadcrumbBar"] .breadcrumb:hover .toolbarbutton-text')
    crumb_arrow = rule('[anonid="breadcrumbBar"] .breadcrumb .breadcrumb-arrow')
    crumbs = rule('[anonid="breadcrumbBar"]')

    hud = rule(".hud")
    disabled_opacity = rule('[disabled="true"]')["opacity"]
    not_found = rule("ko-findbar.ko-findbar-status-not-found .ko-findbar-textbox > *")
    not_found_bg = re.search(r"rgba?\([^)]*\)", not_found["box-shadow"]).group(0)

    find_wrap = rule("#find-box-wrap")
    find_closer = rule("#find-box-closer")
    _closer_width, closer_hover_color = _shadow(rule("#find-box-closer:hover")["box-shadow"])
    glyph_button = rule("#find-next-btn")

    scrollbar = rule("scrollbar")
    scrollbar_v = rule('scrollbar[orient="vertical"]')
    scrollbar_h = rule('scrollbar[orient="horizontal"]')
    thumb = rule("scrollbar thumb")

    textbox = rule("textbox")
    focus_width, focus_color = _shadow(
        rule('textbox:not([disabled="true"]):not([readonly]):focus')["box-shadow"]
    )
    button = rule("button")
    # Regular (styled) buttons; .unstyled/.button-toolbar-a are the
    # exceptions in Komodo, not the rule.
    styled_button = rule(':not(button) > button:not(.button-toolbar-a):not(.unstyled):not(.spinbuttons-button)')
    styled_button_hover = rule(':not(button) > button:not(.button-toolbar-a):not(.unstyled):not(.spinbuttons-button):hover')
    checkbox = rule("checkbox")
    checkbox_checked = rule('checkbox.label-only[checked="true"]')

    workspace_splitter = rule('#komodo_main splitter.workspace_splitter[orient="horizontal"]')
    splitter = rule("splitter:not(.workspace_splitter)")

    tree = rule("tree:not(.bg_transparent) .tree-rows")
    tree_header = rule("tree:not(.bg_transparent) treecol")
    tree_selected = rule("treechildren::-moz-tree-row(selected)")

    return f"""
QWidget {{
    background: {root["background"]};
    color: {root["color"]};
}}

QMenuBar {{
    background: {menubar_bg};
    color: {c["foreground-special"]};
    padding: 0;
}}
QMenuBar::item {{
    background: transparent;
    padding: {menubar_pad_v}px {_px(menu["padding"].split()[1], rem_px)}px;
}}
QMenuBar::item:selected, QMenuBar::item:pressed {{
    background: {popup_active["background"]};
    color: {popup_active["color"]};
}}

QMenu {{
    background: {popup_box["background"]};
    border: {popup_box["border"]};
    border-radius: {popup_box["border-radius"]};
    color: {popup_item["color"]};
}}
QMenu::item {{
    padding: {_box(popup_item["padding"], rem_px)};
    min-height: {_px(popup_item["min-height"], rem_px)}px;
    background: transparent;
}}
QMenu::item:selected {{
    background: {popup_active["background"]};
    color: {popup_active["color"]};
}}
QMenu::item:disabled {{
    color: {_faded(popup_item["color"], disabled_opacity)};
}}
QMenu::separator {{
    height: 1px;
    background: {popup_separator["background"]};
}}

QTabBar[koTabs="true"] {{
    border-bottom: {tab_shadow_width}px solid {tab_shadow_color};
}}
QTabBar[koTabs="true"]::tab {{
    background: transparent;
    color: {tab["color"]};
    padding: {_box(tab["padding"], rem_px)};
    min-height: {_px(tab_strip["min-height"], rem_px) - 2 * tab_shadow_width}px;
    max-width: {file_tab["max-width"]};
    border: 0;
    border-bottom: {tab_unselected["border-bottom"]};
}}
QTabBar[koTabs="true"]::tab:hover:!selected {{
    border-bottom: {tab_hover["border-bottom"]};
}}
QTabBar[koTabs="true"]::tab:selected {{
    border-bottom: {tab_selected["border-bottom"]};
}}
QTabBar[koPaneType="icons"]::tab {{
    padding: {_box(icon_tab["padding"], rem_px)};
}}

QStatusBar {{
    background: {statusbar["background"]};
    border: 0;
    border-top: {statusbar["border-top"]};
    min-height: {_px(statusbar["height"], rem_px) - 1}px;
    max-height: {_px(statusbar["height"], rem_px) - 1}px;
    color: {statusbar_text};
}}
QStatusBar QWidget {{
    background: transparent;
}}
QStatusBar QLabel {{
    color: {statusbar_text};
    padding: {_box(statusbar_label["padding"], rem_px)};
    margin: {_box(statusbar_label["margin"], rem_px)};
}}
QStatusBar QToolButton {{
    color: {statusbar_text};
    border: 0;
    background: transparent;
    padding: {_box(crumb_text["padding"], rem_px)};
    border-radius: {crumb_text["border-radius"]};
}}
QStatusBar QToolButton:hover {{
    background: {crumb_hover["background"]};
    color: {crumb_hover["color"]};
}}
QStatusBar QToolButton::menu-indicator {{
    width: 0;
}}
QStatusBar::item {{
    border: 0;
}}
QWidget#breadcrumbBar {{
    margin: {_box(crumbs["margin"], rem_px)};
}}
QLabel#breadcrumb-arrow {{
    font-family: icomoon;
    font-size: {crumb_arrow["font-size"]};
    color: {crumb_arrow["color"]};
    margin: {_box(crumb_arrow["margin"], rem_px)};
    padding: 0;
}}

QWidget#ko-findbar {{
    background: {hud["background"]};
    color: {hud["color"]};
}}
QWidget#ko-findbar QLabel {{
    background: transparent;
    color: {hud["color"]};
}}
QLineEdit#ko-findbar-textbox[notFound="true"] {{
    background: {not_found_bg};
    color: {not_found["color"]};
}}

QWidget#find-box-closer {{
    min-height: {find_closer["height"]};
    max-height: {find_closer["height"]};
}}
QWidget#find-box-closer:hover {{
    border-top: 4px solid {closer_hover_color};
}}
QWidget#find-box-wrap {{
    padding: {_box(find_wrap["padding"], rem_px)};
}}
QWidget#findReplaceWrap QToolButton {{
    background: transparent;
    border: 0;
    padding: 2px;
}}
QPushButton#find-next-btn, QPushButton#find-prev-btn {{
    padding: {glyph_button["padding"]};
    max-width: {glyph_button["max-width"]};
}}

QScrollBar {{
    background: {scrollbar["background"]};
    border: {scrollbar["border"]};
    margin: {scrollbar["margin"]};
}}
QScrollBar:vertical {{
    width: {_px(scrollbar_v["min-width"], rem_px)}px;
}}
QScrollBar:horizontal {{
    height: {_px(scrollbar_h["min-height"], rem_px)}px;
}}
QScrollBar::handle {{
    background: {thumb["background"]};
    border: {thumb["border"]};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
    border: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

QLineEdit, QComboBox, QSpinBox, QPlainTextEdit#textbox {{
    background: {textbox["background"]};
    color: {textbox["color"]};
    border-radius: {textbox["border-radius"]};
    padding: {_box(textbox["padding"], rem_px)};
    margin: {_box(textbox["margin"], rem_px)};
    min-height: {_px(textbox["min-height"], rem_px)}px;
    border: {focus_width}px solid transparent;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border-color: {focus_color};
}}

QPushButton {{
    background: {styled_button["background"]};
    color: {styled_button["color"]};
    border: 0;
    margin: {_box(styled_button["margin"], rem_px)};
    padding: {_box(styled_button["padding"], rem_px)};
    min-width: {_px(button["min-width"], rem_px)}px;
}}
QPushButton:hover {{
    background: {styled_button_hover["background"]};
    color: {styled_button_hover["color"]};
}}
QPushButton:disabled {{
    color: {_faded(styled_button["color"], disabled_opacity)};
}}
QToolButton {{
    background: transparent;
    color: {button["color"]};
    border: 0;
    border-radius: {popup_box["border-radius"]};
    padding: 2px;
}}
QToolButton:hover {{
    background: {c["button"]};
}}
QToolButton:checked {{
    color: {checkbox_checked["color"]};
}}

QCheckBox {{
    background: transparent;
    color: {checkbox["color"]};
    padding: {_box(checkbox["padding"], rem_px)};
}}

QSplitter::handle, QMainWindow::separator {{
    background: {splitter["background-color"]};
    width: {_px(workspace_splitter["width"], rem_px)}px;
    height: {_px(workspace_splitter["width"], rem_px)}px;
}}

QTreeView, QTreeWidget, QListView {{
    background: {tree["background"]};
    border: 0;
    selection-background-color: {tree_selected["background"]};
    selection-color: {tree_selected["color"]};
}}
QHeaderView::section {{
    background: {tree_header["background"]};
    color: {root["color"]};
    border: 0;
    padding: 2px 4px;
}}
"""


def build_palette():
    """QPalette from Komodo's interface colors, for widgets/dialogs QSS
    doesn't reach (native dialogs, Scintilla's call-tips, ...)."""
    c = load_colors()
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: "background",
        QPalette.ColorRole.WindowText: "foreground",
        QPalette.ColorRole.Base: "textbox",
        QPalette.ColorRole.AlternateBase: "background",
        QPalette.ColorRole.Text: "textbox-foreground",
        QPalette.ColorRole.Button: "button",
        QPalette.ColorRole.ButtonText: "button-foreground",
        QPalette.ColorRole.Highlight: "selected",
        QPalette.ColorRole.HighlightedText: "selected-foreground",
        QPalette.ColorRole.ToolTipBase: "contrast",
        QPalette.ColorRole.ToolTipText: "foreground",
        QPalette.ColorRole.PlaceholderText: "caption",
    }
    for role, name in roles.items():
        palette.setColor(role, QColor(c[name]))
    return palette


def apply(app):
    """Style a QApplication like Komodo. Uses the app font as 1rem, the
    same way Gecko resolves Komodo's `font: message-box` root font."""
    # Komodo draws its own chrome (-moz-appearance: none throughout), so
    # start from Qt's neutral Fusion style rather than the desktop theme.
    app.setStyle("Fusion")
    app.setPalette(build_palette())
    rem_px = app.font().pixelSize()
    if rem_px <= 0:
        rem_px = round(app.font().pointSizeF() * app.primaryScreen().logicalDotsPerInch() / 72)
    app.setStyleSheet(build_qss(rem_px, QFontMetrics(app.font()).height()))
