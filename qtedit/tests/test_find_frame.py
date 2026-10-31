import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from qtedit.editor import CodeEditor  # noqa: E402
from qtedit.find_bar import (  # noqa: E402
    CASE_IGNORE,
    CASE_MATCH,
    CASE_SMART,
    SEARCH_DOCUMENT,
    SEARCH_FILES,
    SEARCH_SELECTION,
    FindFrame,
)

_app = QApplication.instance() or QApplication([])


class FindFrameTestCase(unittest.TestCase):
    def setUp(self):
        self.editor = CodeEditor()
        self.editor.setText("foo Foo foo\nbar foo\n")
        self.frame = FindFrame()
        self.frame.set_editor(self.editor)
        self.messages = []
        self.frame.message.connect(self.messages.append)
        self.hits = []
        self.frame.hits_found.connect(self.hits.append)

    def tearDown(self):
        # Without this, test_python.py's CatalogTestCase hangs when it runs
        # after this module (root cause not tracked down; deleting the
        # widgets avoids it).
        self.frame.deleteLater()
        self.editor.deleteLater()
        _app.processEvents()

    def _selection(self):
        return self.editor.selectionStart(), self.editor.selectionEnd()

    def test_find_next_wraps_around(self):
        self.frame._pattern.setText("bar")
        self.editor.gotoPos(15)
        self.frame.find_next()
        self.assertEqual(self._selection(), (12, 15))

    def test_case_option_cycles_like_komodo(self):
        case = self.frame._opt_case
        self.assertEqual(case.value, CASE_IGNORE)
        case.click()
        self.assertEqual(case.value, CASE_MATCH)
        case.click()
        self.assertEqual(case.value, CASE_SMART)
        case.click()
        self.assertEqual(case.value, CASE_IGNORE)

    def test_smart_case_is_sensitive_only_with_uppercase(self):
        self.frame._opt_case.value = CASE_SMART
        self.frame._pattern.setText("foo")
        self.assertFalse(self.frame._case_sensitive())
        self.frame._pattern.setText("Foo")
        self.assertTrue(self.frame._case_sensitive())

    def test_replace_all_in_document_is_one_undo_step(self):
        self.frame._opt_case.value = CASE_MATCH
        self.frame._pattern.setText("foo")
        self.frame._repl.setText("x")
        self.frame.replace_all()
        self.assertEqual(self.editor.current_text(), "x Foo x\nbar x\n")
        self.editor.undo()
        self.assertEqual(self.editor.current_text(), "foo Foo foo\nbar foo\n")

    def test_replace_all_within_selection(self):
        self.editor.setSel(0, 12)  # whole first line incl. newline
        self.frame.show_bar(replace=True)
        self.assertEqual(self.frame.search_in(), SEARCH_SELECTION)
        self.frame._pattern.setText("foo")
        self.frame._repl.setText("x")
        self.frame.replace_all()
        self.assertEqual(self.editor.current_text(), "x x x\nbar foo\n")

    def test_single_line_selection_preloads_pattern(self):
        self.editor.setSel(12, 15)
        self.frame.show_bar()
        self.assertEqual(self.frame._pattern.text(), "bar")
        self.assertEqual(self.frame.search_in(), SEARCH_DOCUMENT)

    def test_find_all_in_document_reports_hits(self):
        self.frame._pattern.setText("foo")
        self.frame.find_all()
        self.assertEqual(len(self.hits), 1)
        self.assertEqual([h.line_no for h in self.hits[0]], [1, 1, 1, 2])

    def test_files_mode_shows_directory_row(self):
        self.frame.show_bar(search_in=SEARCH_FILES)
        self.assertFalse(self.frame._dirs_box.isHidden())
        self.assertTrue(self.frame._find_next_btn.isHidden())
        self.frame.show_bar(search_in=SEARCH_DOCUMENT)
        self.assertTrue(self.frame._dirs_box.isHidden())
        self.assertFalse(self.frame._find_next_btn.isHidden())
