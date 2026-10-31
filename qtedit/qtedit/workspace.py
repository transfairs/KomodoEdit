"""Komodo's workspace panes (<ko-pane>, see komodo.p.xul's #komodo-hbox).

The main window is laid out the way komodo.p.xul does it:

    workspace_left_area | editor (+ statusbar, find frame) | workspace_right_area
                        | workspace_bottom_area             |

Each pane is a tab strip over a stack of widgets ("ko-widgets"), and the
whole pane collapses rather than being a free-floating dock. Pane tabs use
the IcoMoon glyph Komodo's skin assigns to that widget id
(`tab[widget="placesViewbox"]:before { content: "\\e9dc" }`), so the ids
passed to add_widget() are Komodo's own where one exists.
"""
from PySide6.QtWidgets import QSplitter, QStackedWidget, QTabBar, QVBoxLayout, QWidget

from qtedit import icons
from qtedit.skin.css import komodo_stylesheet

# Pane layout types (ko-pane[type=...]) as persisted by Komodo's xulstore:
# side panes default to icon-only tabs, the bottom pane to icon + label.
TYPE_ICONS = "icons"
TYPE_HORIZONTAL = "horizontal"


def widget_glyph(widget_id, fallback_name=None):
    """The QIcon Komodo's skin gives a pane tab for `widget_id`."""
    content = komodo_stylesheet().value(f'tab[widget="{widget_id}"]:before', "content")
    if content:
        return icons.glyph(icons.css_glyph(content))
    if fallback_name:
        return icons.icon(fallback_name)
    return icons.glyph(" ")


class KoPane(QWidget):
    def __init__(self, pane_id, pane_type, parent=None):
        super().__init__(parent)
        self.setObjectName(pane_id)
        self._type = pane_type
        self._ids = []

        self._tabs = QTabBar()
        self._tabs.setProperty("koTabs", True)
        self._tabs.setProperty("koPaneType", pane_type)
        self._tabs.setDrawBase(False)
        self._tabs.setDocumentMode(True)
        # ko-pane[type="icons"] tab { -moz-box-flex: 1 }: icon tabs share
        # the pane's width instead of packing to the left.
        self._tabs.setExpanding(pane_type == TYPE_ICONS)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        self._stack = QStackedWidget()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._tabs)
        layout.addWidget(self._stack, 1)

    def add_widget(self, widget_id, label, widget, glyph_fallback=None, visible=True):
        """Add a ko-widget tab. Hidden (visible=False) widgets keep their
        tab slot and appear via show_widget(), like Komodo's debug session
        and find results widgets that only exist while in use."""
        icon = widget_glyph(widget_id, glyph_fallback)
        text = "" if self._type == TYPE_ICONS else label
        index = self._tabs.addTab(icon, text)
        self._tabs.setTabToolTip(index, label)
        if not visible:
            # Only ever hide here: setTabVisible(True) on a tab bar's sole
            # tab leaves the bar laid out at zero height (Qt 6.10).
            self._tabs.setTabVisible(index, False)
        self._stack.addWidget(widget)
        self._ids.append(widget_id)
        return index

    def set_label(self, widget_id, label):
        index = self._ids.index(widget_id)
        self._tabs.setTabToolTip(index, label)
        if self._type != TYPE_ICONS:
            self._tabs.setTabText(index, label)

    def set_widget(self, widget_id, widget):
        """Replace a tab's content widget (e.g. a panel rebuilt for a new
        project), keeping its tab."""
        index = self._ids.index(widget_id)
        old = self._stack.widget(index)
        self._stack.insertWidget(index, widget)
        self._stack.removeWidget(old)
        if self._tabs.currentIndex() == index:
            self._stack.setCurrentIndex(index)

    def set_widget_visible(self, widget_id, visible):
        index = self._ids.index(widget_id)
        if self._tabs.isTabVisible(index) != visible:
            self._tabs.setTabVisible(index, visible)

    def show_widget(self, widget_id):
        """Select a widget's tab and uncollapse the pane, as Komodo's
        ko.widgets.getWidgetAsync(...).show() does."""
        self.set_widget_visible(widget_id, True)
        self._tabs.setCurrentIndex(self._ids.index(widget_id))
        self.setVisible(True)

    def visible_widgets(self):
        """(widget id, label) for each tab currently shown, in tab order."""
        return [
            (widget_id, self._tabs.tabToolTip(i))
            for i, widget_id in enumerate(self._ids)
            if self._tabs.isTabVisible(i)
        ]

    def current_widget_id(self):
        index = self._tabs.currentIndex()
        return self._ids[index] if index >= 0 else None

    def toggle(self):
        self.setVisible(not self.isVisible())

    def _on_tab_changed(self, index):
        if index >= 0:
            self._stack.setCurrentIndex(index)


def make_splitter(orientation, object_name):
    """A QSplitter styled as Komodo's .workspace_splitter."""
    splitter = QSplitter(orientation)
    splitter.setObjectName(object_name)
    splitter.setChildrenCollapsible(False)
    splitter.setHandleWidth(5)
    return splitter

