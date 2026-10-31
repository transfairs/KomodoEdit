import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from qtedit.editor import CodeEditor  # noqa: E402
from qtedit.incremental_search import (  # noqa: E402
    FOC_SMART,
    FOT_SIMPLE,
    FOT_WILDCARD,
    IncrementalSearchBar,
)

_app = QApplication.instance() or QApplication([])


class IncrementalSearchTestCase(unittest.TestCase):
    def setUp(self):
        self.editor = CodeEditor()
        self.editor.setText("alpha beta\nAlpha gamma\nalphabet\n")
        self.bar = IncrementalSearchBar()
        # Komodo's defaults, independent of whatever the prefs file holds.
        self.bar.case_sensitivity = FOC_SMART
        self.bar.pattern_type = FOT_SIMPLE

    def tearDown(self):
        # Same as test_find_frame.py: leftover widgets stall test_python.py.
        self.bar.deleteLater()
        self.editor.deleteLater()
        _app.processEvents()

    def _selection(self):
        return self.editor.selectionStart(), self.editor.selectionEnd()

    def _type(self, text):
        self.bar._textbox.setText(text)
        self.bar._on_input(text)

    def test_typing_searches_from_start_position(self):
        self.editor.gotoPos(5)
        self.bar.start(self.editor)
        self._type("alpha")
        # Smart case + lowercase pattern: "Alpha" on line 2 matches first.
        self.assertEqual(self._selection(), (11, 16))
        self._type("alp")
        self.assertEqual(self._selection(), (11, 14))

    def test_smart_case_with_uppercase_is_sensitive(self):
        self.bar.start(self.editor)
        self._type("Alpha")
        self.assertEqual(self._selection(), (11, 16))

    def test_search_again_wraps(self):
        self.bar.start(self.editor)
        self._type("gamma")
        self.bar.search_again()
        self.assertEqual(self._selection(), (17, 22))
        self.assertIn("continued from top", self.bar._status.text())

    def test_not_found_marks_textbox(self):
        self.bar.start(self.editor)
        self._type("zeta")
        self.assertTrue(self.bar._textbox.property("notFound"))

    def test_selection_preloads_pattern(self):
        self.editor.setSel(6, 10)
        self.bar.start(self.editor)
        self.assertEqual(self.bar._textbox.text(), "beta")

    def test_wildcard_pattern(self):
        self.bar.pattern_type = FOT_WILDCARD
        self.bar.start(self.editor)
        self._type("g?mm*")
        start, _end = self._selection()
        self.assertEqual(start, 17)
