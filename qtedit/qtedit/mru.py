"""Recent Files / Recent Projects / Recently Closed Tabs, as in Komodo.

Ports ko.mru (library/mru.js), the MRU menu builder in
library/uilayout.p.js (_doUpdateMRUMenu) and the closed-tabs stack in
library/history.js (rctabs_*). MRU lists are plain path lists in the
global prefs under Komodo's pref names (mruFileList, mruProjectList), sized
by mruFileSize/mruProjectSize.
"""
import os

from PySide6.QtWidgets import QMenu

FILE_LIST = "mruFileList"
PROJECT_LIST = "mruProjectList"
_SIZE_PREFS = {FILE_LIST: "mruFileSize", PROJECT_LIST: "mruProjectSize"}
# library.properties "Files"/"Projects", used in "No Recent %S".
_PRETTY_NAMES = {FILE_LIST: "Files", PROJECT_LIST: "Projects"}
PROJECT_EXTENSION = ".komodoproject"

# history.js rctab_list_max_size
CLOSED_TABS_MAX = 10


def entries(prefs, pref_name):
    return list(prefs.get(pref_name) or [])


def add(prefs, pref_name, path):
    """MRU_add: move/insert at the top, trimmed to the size pref."""
    max_entries = prefs.get(_SIZE_PREFS[pref_name])
    items = [p for p in entries(prefs, pref_name) if os.path.normcase(p) != os.path.normcase(path)]
    if max_entries > 0:
        items = [path] + items[:max_entries - 1]
    prefs.set(pref_name, items)


def remove(prefs, pref_name, path):
    items = entries(prefs, pref_name)
    if path in items:
        items.remove(path)
        prefs.set(pref_name, items)


def _accesskey_label(number, text):
    """Komodo puts accesskeys 1-9, 0 on the first ten items only."""
    text = text.replace("&", "&&")
    if number <= 9:
        return f"&{number} {text}"
    if number == 10:
        return f"1&0 {text}"
    return f"{number} {text}"


def fill_menu(menu, prefs, pref_name, open_path, limit=0, manage=None, icon_for=None):
    """_doUpdateMRUMenu. Entries past `limit` go into a "More" submenu
    (Recent Projects uses 5); missing files are dropped from the list.
    manage: (label, callback) for the "Manage the ... List" item, or None."""
    items = entries(prefs, pref_name)
    existing = [p for p in items if os.path.exists(p)]
    if existing != items:
        prefs.set(pref_name, existing)
    if not existing:
        empty = menu.addAction(f"No Recent {_PRETTY_NAMES[pref_name]}")
        empty.setEnabled(False)
        return
    target = menu
    number = 1
    for index, path in enumerate(existing):
        if limit and index == limit and limit < len(existing) - 1:
            # An explicit parent: the QMenu that addMenu(str) returns is
            # deleted with its Python wrapper.
            target = QMenu("&More", menu)
            menu.addMenu(target)
            if manage is not None:
                _add_manage_item(menu, manage)
                manage = None
            number = 1
        name = os.path.basename(path)
        if pref_name == PROJECT_LIST and name.endswith(PROJECT_EXTENSION):
            name = name[:-len(PROJECT_EXTENSION)]
        action = target.addAction(_accesskey_label(number, name))
        action.setToolTip(path)
        if icon_for is not None:
            action.setIcon(icon_for(path))
        action.triggered.connect(lambda _c=False, p=path: open_path(p))
        number += 1
    if manage is not None:
        _add_manage_item(menu, manage)
    menu.setToolTipsVisible(True)


def _add_manage_item(menu, manage):
    label, callback = manage
    menu.addSeparator()
    action = menu.addAction(label)
    if callback is None:
        action.setEnabled(False)
    else:
        action.triggered.connect(lambda _c=False: callback())


class ClosedTabs:
    """history.js's rctabs stack (in memory, like Komodo's)."""

    def __init__(self):
        self._paths = []

    def note(self, path):
        if not path:
            return
        if path in self._paths:
            self._paths.remove(path)
        self._paths.append(path)
        del self._paths[:-CLOSED_TABS_MAX]

    def pop(self):
        return self._paths.pop() if self._paths else None

    def fill_menu(self, menu: QMenu, reopen, shortcut_text=None):
        if not self._paths:
            menu.addAction("No tabs to reopen").setEnabled(False)
            return
        for number, path in enumerate(reversed(self._paths), start=1):
            label = _accesskey_label(number, os.path.basename(path))
            if number == 1 and shortcut_text:
                label += f"\t{shortcut_text}"  # the cmd_reopenLastClosedTab item
            action = menu.addAction(label)
            action.setToolTip(path)
            action.triggered.connect(lambda _c=False, p=path: reopen(p))
        menu.setToolTipsVisible(True)

    def discard(self, path):
        if path in self._paths:
            self._paths.remove(path)
