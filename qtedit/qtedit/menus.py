"""Komodo's main menubar, built from skin/komodo12/menus.json.

The snapshot is komodo.xul's #menubar_main with all overlays merged and
entities resolved (tools/extract_komodo_menus.py), so labels, order,
separators, accesskeys and Legacy-scheme shortcuts are Komodo's own.
Menu items are wired by Komodo command id (cmd_save, cmd_find, ...) to a
registry of qtedit callbacks. Items whose command qtedit doesn't implement
yet stay visible but disabled, showing their shortcut as text only so an
unimplemented chord can't swallow keys meant for the editor.
"""
import json
import os
from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMenu

MENUS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skin", "komodo12", "menus.json")

# .kkf key names that differ from QKeySequence's.
_KEY_NAMES = {
    "Page_Down": "PgDown",
    "Page_Up": "PgUp",
    "Escape": "Esc",
    "Return": "Return",
}


def kkf_to_sequence(binding):
    """'Ctrl+K Ctrl+J' (a .kkf chord) -> QKeySequence('Ctrl+K, Ctrl+J')."""
    chords = []
    for chord in binding.split():
        parts = chord.split("+")
        # "Ctrl++" splits into [..., "", ""]: the key itself is "+".
        if chord.endswith("++"):
            parts = parts[:-2] + ["+"]
        parts[-1] = _KEY_NAMES.get(parts[-1], parts[-1])
        chords.append("+".join(parts))
    return QKeySequence(", ".join(chords))


@dataclass
class Command:
    run: Callable[[], None]
    checked: Optional[Callable[[], bool]] = None
    enabled: Optional[Callable[[], bool]] = None


def load_menus(path=MENUS_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["menus"]


def load_bindings(path=MENUS_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["bindings"]


def _with_accesskey(label, accesskey):
    """XUL puts the accesskey in its own attribute; Qt wants an '&'."""
    label = label.replace("&", "&&")
    if accesskey:
        index = label.lower().find(accesskey.lower())
        if index >= 0:
            return label[:index] + "&" + label[index:]
    return label


class MenuBuilder:
    def __init__(self, parent, commands, dynamic_menus=None):
        """commands: {command id: Command}; dynamic_menus: {menu id:
        callable(QMenu)} for popups Komodo fills at runtime (recent
        files, View as Language, Tabs & Sidebars, ...)."""
        self._parent = parent
        self._commands = commands
        self._dynamic = dynamic_menus or {}
        self.actions = {}  # command id -> QAction

    def build(self, menubar, nodes=None, extra_menus=()):
        """extra_menus: [(insert_after_label, QMenu)] for qtedit menus
        Komodo Edit doesn't have (e.g. Komodo IDE's Debug menu)."""
        for node in nodes if nodes is not None else load_menus():
            if node.get("hidden"):
                continue
            menu = self._build_menu(node, menubar)
            menubar.addMenu(menu)
            for after, extra in extra_menus:
                if after == node["label"]:
                    menubar.addMenu(extra)
        return menubar

    def _build_menu(self, node, parent):
        menu = QMenu(_with_accesskey(node["label"], node.get("accesskey")), parent)
        menu.setObjectName(node.get("id") or "")
        filler = self._dynamic.get(node.get("id"))
        if filler is not None:
            menu.aboutToShow.connect(lambda m=menu, f=filler: (m.clear(), f(m)))
            return menu
        if not node["children"]:
            menu.setEnabled(False)
            return menu
        for child in node["children"]:
            if child.get("hidden"):
                continue
            if child["type"] == "separator":
                menu.addSeparator()
            elif child["type"] == "menu":
                menu.addMenu(self._build_menu(child, menu))
            else:
                menu.addAction(self._build_action(child, menu))
        menu.aboutToShow.connect(lambda m=menu: self._refresh(m))
        menu.aboutToHide.connect(lambda m=menu: self._reenable(m))
        _drop_redundant_separators(menu)
        return menu

    def _build_action(self, node, menu):
        label = _with_accesskey(node["label"], node.get("accesskey"))
        command_id = node.get("command")
        command = self._commands.get(command_id)
        shortcut = node.get("shortcut")
        # Text after a tab is what QMenu shows as accelerator; using the
        # .kkf string keeps Komodo's chord notation ("Ctrl+K Ctrl+V").
        action = QAction(f"{label}\t{shortcut}" if shortcut else label, menu)
        action.setData(command_id)
        if command is None:
            action.setEnabled(False)
            return action
        if shortcut:
            action.setShortcut(kkf_to_sequence(shortcut))
        if node.get("checkable") or command.checked is not None:
            action.setCheckable(True)
        action.triggered.connect(lambda _checked=False, c=command: c.run())
        # Shortcuts must work with the menu closed, so the action lives on
        # the window too.
        self._parent.addAction(action)
        self.actions[command_id] = action
        return action

    def _refresh(self, menu):
        for action in menu.actions():
            command = self._commands.get(action.data())
            if command is None:
                continue
            if command.enabled is not None:
                action.setEnabled(command.enabled())
            if command.checked is not None:
                action.setChecked(command.checked())


    def _reenable(self, menu):
        """Enabled state is for the open menu only. As in Komodo, where
        keybindings skip the is-enabled test and each command checks for
        itself, a shortcut must keep working after its item was shown
        greyed out (Ctrl+/ after opening Code in a comment-less buffer)."""
        for action in menu.actions():
            command = self._commands.get(action.data())
            if command is not None and command.enabled is not None:
                action.setEnabled(True)


def _drop_redundant_separators(menu):
    """Hidden items can leave leading/trailing/doubled separators behind."""
    previous_separator = True
    actions = menu.actions()
    for action in actions:
        if action.isSeparator():
            if previous_separator:
                menu.removeAction(action)
            previous_separator = True
        else:
            previous_separator = False
    actions = menu.actions()
    if actions and actions[-1].isSeparator():
        menu.removeAction(actions[-1])


def add_window_shortcut(parent, binding, run):
    """A command with a keybinding but no menu item (cmd_viewBottomPane)."""
    action = QAction(parent)
    action.setShortcut(kkf_to_sequence(binding))
    action.triggered.connect(lambda _checked=False: run())
    parent.addAction(action)
    return action
