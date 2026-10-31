import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

from qtedit.quickstart import BUTTON_SIZE, QuickStartButton, QuickStartView  # noqa: E402
from qtedit.statusbar import StatusbarMenuButton  # noqa: E402

_app = QApplication.instance() or QApplication([])


class QuickStartTestCase(unittest.TestCase):
    def setUp(self):
        self.filled = []
        self.view = QuickStartView(lambda kind, menu: self.filled.append(kind))
        self.view.resize(1150, 645)
        self.view.show()
        _app.processEvents()
        self.buttons = {b.accessibleName(): b for b in self.view.findChildren(QuickStartButton)}

    def tearDown(self):
        self.view.deleteLater()
        _app.processEvents()

    def test_quickstart_xml_buttons(self):
        self.assertEqual(list(self.buttons), [
            "New File", "New File from Template", "New Project", "Open File", "Open Project",
            "Preferences", "Install Packages", "Customize Panes", "Troubleshooting", "Report a Bug"])
        self.assertEqual(self.buttons["New File"].size(), BUTTON_SIZE)

    def test_buttons_run_komodo_commands(self):
        commands = []
        self.view.run_command.connect(commands.append)
        self.buttons["New File"].click()
        self.buttons["Open Project"].click()
        self.assertEqual(commands, ["cmd_new", "cmd_openProject"])

    def test_menu_buttons_ask_for_recent_items(self):
        self.buttons["Open File"].menu().aboutToShow.emit()
        self.assertEqual(self.filled, ["mru_files"])

    def test_groups_are_spaced_like_komodo(self):
        new_project = self.buttons["New Project"].geometry()
        open_file = self.buttons["Open File"].geometry()
        new_file = self.buttons["New File"].geometry()
        template = self.buttons["New File from Template"].geometry()
        self.assertEqual(template.top() - new_file.bottom() - 1, 8)
        self.assertEqual(open_file.top() - new_project.bottom() - 1, 23)

    def test_editor_like_surface(self):
        self.assertIsNone(self.view.filepath)
        self.assertFalse(self.view.modify())


class StatusbarMenuButtonTestCase(unittest.TestCase):
    def test_size_hint_has_no_qt_menu_indicator(self):
        button = StatusbarMenuButton()
        button.setText("UTF-8")
        button.setMenu(QMenu(button))
        expected = (2 * (StatusbarMenuButton.PANEL_PADDING + 2) + StatusbarMenuButton.MARKER_SPACE
                    + button.fontMetrics().horizontalAdvance("UTF-8"))
        self.assertEqual(button.sizeHint().width(), expected)
        button.deleteLater()
