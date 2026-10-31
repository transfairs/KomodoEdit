"""Komodo's "New Tab" quick start view (chrome/komodo/content/quickstart.xml).

What cmd_newTab opens, and what Komodo shows when no file is open: a
centred column of buttons (new file/template/project, open file/project
with their recent-items menus, preferences, packages, customize panes) and
a Troubleshooting / Report a Bug footer. Geometry follows the skin rules
(`.inner > button` is 210px wide) and a Komodo 12.10 screenshot
(docs/reference/komodo-12.10-quickstart.png): 29px buttons 8px apart,
15px spacers between the groups.

It sits in the editor tab bar like Komodo's view, so it carries the few
attributes main_window's tab loops read from editors.
"""
from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QMenu, QPushButton, QVBoxLayout, QWidget

from qtedit import icons
from qtedit.skin.css import komodo_stylesheet

TITLE = "New Tab"  # the view's title property / komodo.properties newTab
BUTTON_SIZE = QSize(210, 29)
BUTTON_GAP = 8
GROUP_GAP = 15  # <xul:hbox height="15"/>
GLYPH_PX = 14
FOOTER_PADDING = 22  # styled button padding 0.3rem 1.5rem
FOOTER_MARGIN = 4  # styled button margin

# (label, command id, glyph selector, menu kind) per quickstart.xml.
COLUMN = [
    [("New File", "cmd_new", ".new-file-icon:before", None),
     ("New File from Template", "cmd_newTemplate", ".new-template-icon:before", None),
     ("New Project", "cmd_newProject", ".project-icon:before", None)],
    [("Open File", "cmd_open",
      'vbox[anonid="quickstart"] .open-file-icon-quickstart > .box-inherit:before', "mru_files"),
     ("Open Project", "cmd_openProject",
      'vbox[anonid="quickstart"] .project-icon-quickstart > .box-inherit:before', "mru_projects")],
    [("Preferences", "cmd_editPrefs", ".preferences-icon:before", None),
     ("Install Packages", None,
      'vbox[anonid="quickstart"] .packages-icon-quickstart > .box-inherit:before', "packages"),
     ("Customize Panes", None, ".customize-panes-icon:before", None)],
]
PACKAGE_ITEMS = ["Install Addons", "Install Macros", "Install Toolbox Items",
                 "Install Color Schemes", "Install Skins", "Install Languages",
                 "Install Keybindings"]
TROUBLESHOOTING_ITEMS = ["Restart in Safe-Mode", "Restart Without Addons", "Restart Without Tools",
                         None, "Reset Everything", "Reset File Preferences", "Reset UI Setup",
                         "Reset CodeIntel Database", "Reset Caches", None,
                         "View Log File", "Memory Usage", "Report a Bug"]  # komodo.dtd labels
BUG_DATABASE_URL = "https://github.com/Komodo/KomodoEdit/issues"  # browse.js tag "bugs"


class QuickStartButton(QPushButton):
    """A styled Komodo button: glyph on the left, label centred in the
    rest, and for type="menu-button" a dropmarker on the right."""

    def __init__(self, label, glyph, menu=None, parent=None, footer=False):
        super().__init__(parent)
        self._footer = footer
        self._label = label
        self._glyph = glyph
        self._dropmarker = None
        if menu is not None:
            css = komodo_stylesheet()
            self._dropmarker = icons.glyph(icons.css_glyph(css.value("dropmarker:before", "content")),
                                           16, QColor(css.value("dropmarker:before", "color")), 10)
            self.setMenu(menu)
        self.setObjectName("quickstart-button")
        self.setAccessibleName(label)

    def paintEvent(self, event):
        super().paintEvent(event)  # background/hover from the QSS
        painter = QPainter(self)
        rect = self.rect()
        painter.setPen(self.palette().buttonText().color())
        top = (rect.height() - 16) // 2
        if self._footer:
            # A plain styled button: 1.5rem padding, then icon, label and
            # dropmarker packed to the left.
            x = FOOTER_PADDING
            if self._glyph is not None:
                self._glyph.paint(painter, QRect(x, top, 16, 16))
                x += 16
            text_width = self.fontMetrics().horizontalAdvance(self._label)
            painter.drawText(QRect(x, 0, text_width, rect.height()), Qt.AlignmentFlag.AlignVCenter,
                             self._label)
            if self._dropmarker is not None:
                self._dropmarker.paint(painter, QRect(x + text_width, top, 16, 16))
        else:
            if self._glyph is not None:
                self._glyph.paint(painter, QRect(6, top, 16, 16))
            painter.drawText(QRect(22, 0, rect.width() - 34, rect.height()), Qt.AlignmentFlag.AlignCenter,
                             self._label)
            if self._dropmarker is not None:
                self._dropmarker.paint(painter, QRect(rect.width() - 20, top, 16, 16))
        painter.end()


class QuickStartView(QWidget):
    run_command = Signal(str)  # Komodo command id
    open_url = Signal(str)

    # What main_window's tab loops read from editors.
    filepath = None
    toolbox_item = None
    tab_title = TITLE

    def __init__(self, fill_menu, parent=None):
        """fill_menu(kind, QMenu) fills the recent files/projects menus."""
        super().__init__(parent)
        self.setObjectName("view-quickstart")
        self._fill_menu = fill_menu
        css = komodo_stylesheet()

        column = QVBoxLayout()
        column.setSpacing(BUTTON_GAP)
        column.addStretch(1)
        for group_index, group in enumerate(COLUMN):
            if group_index:
                column.addSpacing(GROUP_GAP)
            for label, command, glyph_rule, menu_kind in group:
                button = self._button(css, label, glyph_rule, menu_kind)
                if command is not None:
                    button.clicked.connect(lambda _c=False, c=command: self.run_command.emit(c))
                elif menu_kind is None:
                    button.setEnabled(False)  # ko.uilayout.customize(): no pane editor yet
                column.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addStretch(1)

        footer = QHBoxLayout()
        footer.setContentsMargins(FOOTER_MARGIN, FOOTER_MARGIN, FOOTER_MARGIN, FOOTER_MARGIN)
        footer.setSpacing(2 * FOOTER_MARGIN)
        footer.addStretch(1)
        troubleshooting = self._button(
            css, "Troubleshooting", 'vbox[anonid="quickstart"] .help-icon-quickstart > .box-inherit:before',
            "troubleshooting", footer=True)
        bug = self._button(css, "Report a Bug", ".bug-icon:before", None, footer=True)
        bug.clicked.connect(lambda: self.open_url.emit(BUG_DATABASE_URL))
        footer.addWidget(troubleshooting)
        footer.addWidget(bug)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(column, 1)
        layout.addLayout(footer)

    def _button(self, css, label, glyph_rule, menu_kind, footer=False):
        glyph = icons.glyph(icons.css_glyph(css.value(glyph_rule, "content")), 16,
                            QColor(css.value(glyph_rule, "color", "#ffffff")), GLYPH_PX)
        menu = None
        if menu_kind is not None:
            menu = QMenu(self)
            menu.aboutToShow.connect(lambda m=menu, k=menu_kind: self._fill(k, m))
        button = QuickStartButton(label, glyph, menu, self, footer)
        if footer:
            width = (button.fontMetrics().horizontalAdvance(label) + 2 * FOOTER_PADDING + 16
                     + (16 if menu else 0))
        else:
            width = BUTTON_SIZE.width()
        # The global QPushButton rule's padding, margin and min-width would
        # override a fixed size; these buttons draw their own content.
        button.setStyleSheet(
            f"QPushButton {{ margin: 0; padding: 0; border: 0; min-width: {width}px; max-width: {width}px;"
            f" min-height: {BUTTON_SIZE.height()}px; max-height: {BUTTON_SIZE.height()}px; }}"
            " QPushButton::menu-indicator { image: none; width: 0; }")
        return button

    def _fill(self, kind, menu):
        menu.clear()
        if kind == "packages":
            for label in PACKAGE_ITEMS:
                menu.addAction(label).setEnabled(False)  # no package scope in qtedit
        elif kind == "troubleshooting":
            for label in TROUBLESHOOTING_ITEMS:
                if label is None:
                    menu.addSeparator()
                elif label == "Report a Bug":
                    menu.addAction(label).triggered.connect(lambda: self.open_url.emit(BUG_DATABASE_URL))
                else:
                    menu.addAction(label).setEnabled(False)
        else:
            self._fill_menu(kind, menu)

    # Editor-like surface for main_window's tab loops.
    def modify(self):
        return False

    def current_text(self):
        return ""
