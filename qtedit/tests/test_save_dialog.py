import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from qtedit.save_dialog import SaveModifiedDialog  # noqa: E402

_app = QApplication.instance() or QApplication([])


class SaveModifiedDialogTestCase(unittest.TestCase):
    def ask(self, prepare, button_text):
        dialog = SaveModifiedDialog(["/a.py", "/b.py", "untitled"])

        def answer():
            prepare(dialog)
            [b for b in dialog.findChildren(type(dialog._save)) if b.text() == button_text][0].click()

        QTimer.singleShot(0, answer)
        try:
            return dialog.ask()
        finally:
            dialog.deleteLater()
            _app.processEvents()

    def test_all_selected_by_default(self):
        self.assertEqual(self.ask(lambda d: None, "Save"), [0, 1, 2])

    def test_deselected_items_are_not_saved(self):
        self.assertEqual(self.ask(lambda d: d.list.item(1).setSelected(False), "Save"), [0, 2])

    def test_do_not_save_and_cancel(self):
        self.assertEqual(self.ask(lambda d: None, "Do Not Save"), [])
        self.assertIsNone(self.ask(lambda d: None, "Cancel"))
