import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QKeySequence  # noqa: E402
from PySide6.QtWidgets import QApplication, QMainWindow  # noqa: E402

from qtedit.menus import Command, MenuBuilder, kkf_to_sequence, load_menus  # noqa: E402

_app = QApplication.instance() or QApplication([])


class KkfTestCase(unittest.TestCase):
    def test_chords_and_special_keys(self):
        self.assertEqual(kkf_to_sequence("Ctrl+K Ctrl+J"), QKeySequence("Ctrl+K, Ctrl+J"))
        self.assertEqual(kkf_to_sequence("Ctrl++"), QKeySequence("Ctrl++"))
        self.assertEqual(kkf_to_sequence("Shift+Page_Down"), QKeySequence("Shift+PgDown"))


class MenuBuilderTestCase(unittest.TestCase):
    NODES = [{
        "type": "menu", "id": "menu_file", "label": "File", "accesskey": "F",
        "children": [
            {"type": "menuitem", "id": "a", "label": "Save", "command": "cmd_save", "shortcut": "Ctrl+S"},
            {"type": "separator"},
            {"type": "menuitem", "id": "b", "label": "Revert", "command": "cmd_revert", "shortcut": "Ctrl+K R"},
            {"type": "menuitem", "id": "c", "label": "Hidden", "hidden": True},
        ],
    }]

    def setUp(self):
        self.window = QMainWindow()
        self.saved = []
        self.builder = MenuBuilder(self.window, {"cmd_save": Command(lambda: self.saved.append(1))})
        self.builder.build(self.window.menuBar(), self.NODES)
        self.items = [a for a in self.window.menuBar().actions()[0].menu().actions()]

    def tearDown(self):
        self.window.deleteLater()
        _app.processEvents()

    def test_accesskey_becomes_mnemonic(self):
        self.assertEqual(self.window.menuBar().actions()[0].text(), "&File")

    def test_implemented_command_is_bound(self):
        save = self.builder.actions["cmd_save"]
        self.assertEqual(save.shortcut(), QKeySequence("Ctrl+S"))
        save.trigger()
        self.assertEqual(self.saved, [1])

    def test_unimplemented_command_is_disabled_and_unbound(self):
        revert = [a for a in self.items if a.data() == "cmd_revert"][0]
        self.assertFalse(revert.isEnabled())
        self.assertTrue(revert.shortcut().isEmpty())
        self.assertTrue(revert.text().endswith("\tCtrl+K R"))

    def test_hidden_items_are_skipped(self):
        self.assertEqual(len([a for a in self.items if not a.isSeparator()]), 2)


class SnapshotTestCase(unittest.TestCase):
    def test_komodo_menubar_order(self):
        labels = [m["label"] for m in load_menus() if not m.get("hidden")]
        self.assertEqual(
            labels,
            ["File", "Edit", "Code", "Navigation", "View", "Project", "Tools", "Help", "Test"],
        )


class EnabledStateTestCase(unittest.TestCase):
    NODES = [{
        "type": "menu", "id": "menu_code", "label": "Code", "accesskey": "C",
        "children": [
            {"type": "menuitem", "id": "a", "label": "Comment", "command": "cmd_comment", "shortcut": "Ctrl+/"},
        ],
    }]

    def setUp(self):
        self.window = QMainWindow()
        self.ran = []
        builder = MenuBuilder(self.window, {
            "cmd_comment": Command(lambda: self.ran.append(1), enabled=lambda: False),
        })
        builder.build(self.window.menuBar(), self.NODES)
        self.menu = self.window.menuBar().actions()[0].menu()
        self.action = builder.actions["cmd_comment"]

    def tearDown(self):
        self.window.deleteLater()
        _app.processEvents()

    def test_shortcut_works_again_after_menu_closes(self):
        self.menu.aboutToShow.emit()
        self.assertFalse(self.action.isEnabled())
        self.menu.aboutToHide.emit()
        self.assertTrue(self.action.isEnabled())
