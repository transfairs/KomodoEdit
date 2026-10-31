import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from qtedit import editor_commands as ec  # noqa: E402
from qtedit.editor import CodeEditor  # noqa: E402

_app = QApplication.instance() or QApplication([])

PYTHON = {"line": ["# ", "#"]}
CPP = {"line": ["//"], "block": [["/*", "*/"]], "markup": "*"}
HTML = {"block": [["<!--", "-->"]]}


class EditorTestCase(unittest.TestCase):
    def setUp(self):
        self.editor = CodeEditor()

    def tearDown(self):
        # Same as test_find_frame.py: leftover widgets stall test_python.py.
        self.editor.deleteLater()
        _app.processEvents()

    def set_text(self, text):
        self.editor.setText(text)

    def text(self):
        return self.editor.current_text()

    def select_lines(self, first, last):
        """Whole lines first..last, ending at the start of the next line."""
        self.editor.setSel(self.editor.positionFromLine(first), self.editor.positionFromLine(last + 1))


class DelimiterLookupTestCase(unittest.TestCase):
    def test_komodo_names_and_pygments_aliases(self):
        self.assertEqual(ec.comment_delimiters(["Python"]), PYTHON)
        # Pygments says "Batchfile", Komodo "Batch".
        self.assertEqual(ec.comment_delimiters(["Batchfile", "batch", "bat"]), {"line": ["rem ", "REM "]})
        self.assertIsNone(ec.comment_delimiters(["NoSuchLanguage"]))


class CommentTestCase(EditorTestCase):
    def test_line_comment_uses_common_indent(self):
        self.set_text("def f():\n    a = 1\n        b = 2\nc\n")
        self.select_lines(1, 2)
        ec.comment(self.editor, PYTHON)
        self.assertEqual(self.text(), "def f():\n    # a = 1\n    #     b = 2\nc\n")

    def test_uncomment_accepts_any_listed_prefix(self):
        self.set_text("    # a\n    #b\nc\n")
        self.select_lines(0, 1)
        ec.uncomment(self.editor, PYTHON)
        self.assertEqual(self.text(), "    a\n    b\nc\n")

    def test_caret_only_comments_its_line_and_keeps_column(self):
        self.set_text("x = 1\ny = 2\n")
        self.editor.gotoPos(8)  # "y |= 2"... column 2 of line 1
        ec.comment(self.editor, PYTHON)
        self.assertEqual(self.text(), "x = 1\n# y = 2\n")
        self.assertEqual(self.editor.currentPos(), 10)

    def test_partial_line_selection_prefers_block(self):
        self.set_text("int a = b + c;\n")
        self.editor.setSel(8, 13)  # "b + c"
        ec.comment(self.editor, CPP)
        self.assertEqual(self.text(), "int a = /*b + c*/;\n")
        ec.uncomment(self.editor, CPP)
        self.assertEqual(self.text(), "int a = b + c;\n")

    def test_block_only_language(self):
        # A selection gets one block comment around it (Komodo checks
        # "no 'line' key and selStart < selEnd" before falling back) ...
        self.set_text("<p>\n<b>\n")
        self.select_lines(0, 1)
        ec.comment(self.editor, HTML)
        self.assertEqual(self.text(), "<!--<p>\n<b>\n-->")
        # ... while a bare caret comments its line with the block pair.
        self.set_text("<p>\n<b>\n")
        self.editor.gotoPos(1)
        ec.comment(self.editor, HTML)
        self.assertEqual(self.text(), "<!--<p>-->\n<b>\n")
        ec.uncomment(self.editor, HTML)
        self.assertEqual(self.text(), "<p>\n<b>\n")

    def test_comment_is_one_undo_step(self):
        self.set_text("a\nb\n")
        self.select_lines(0, 1)
        ec.comment(self.editor, PYTHON)
        self.editor.undo()
        self.assertEqual(self.text(), "a\nb\n")


class TextCommandTestCase(EditorTestCase):
    def test_title_case_and_hex(self):
        self.assertEqual(ec.title_case("hello  wide world"), "Hello  Wide World")
        self.assertEqual(ec.from_hex(ec.to_hex("ä1")), "ä1")

    def test_convert_by_line_keeps_selection(self):
        self.set_text("straße\nab\n")
        self.editor.setSel(0, self.editor.lineEndPosition(1))
        ec.convert_selection_by_line(self.editor, str.upper)
        self.assertEqual(self.text(), "STRASSE\nAB\n")
        self.assertEqual(self.editor.selectionEnd(), self.editor.lineEndPosition(1))

    def test_tabify_whole_buffer_without_selection(self):
        self.set_text("        a\n    b\n\tc  d\n")
        ec.tabify(self.editor, 4)
        self.assertEqual(self.text(), "\t\ta\n\tb\n\tc  d\n")
        ec.untabify(self.editor, 4)
        self.assertEqual(self.text(), "        a\n    b\n    c  d\n")

    def test_join(self):
        self.set_text("foo   \n   bar\nbaz\n")
        self.editor.gotoPos(0)
        ec.join_lines(self.editor)
        self.assertEqual(self.text(), "foo bar\nbaz\n")

    def test_remove_trailing_whitespace(self):
        self.set_text("a  \nb\t\n")
        ec.remove_trailing_whitespace(self.editor)
        self.assertEqual(self.text(), "a\nb\n")


class NavigationTestCase(EditorTestCase):
    def test_bookmarks_cycle_and_wrap(self):
        self.set_text("\n".join("line%d" % i for i in range(10)))
        for line in (2, 7):
            self.editor.gotoLine(line)
            ec.toggle_bookmark(self.editor)
        self.editor.gotoLine(0)
        self.assertTrue(ec.goto_next_bookmark(self.editor))
        self.assertEqual(self.editor.lineFromPosition(self.editor.currentPos()), 2)
        self.assertTrue(ec.goto_previous_bookmark(self.editor))  # wraps to 7
        self.assertEqual(self.editor.lineFromPosition(self.editor.currentPos()), 7)
        ec.remove_all_bookmarks(self.editor)
        self.assertFalse(ec.goto_next_bookmark(self.editor))

    def test_toggle_bookmark_twice_removes_it(self):
        self.set_text("a\nb\n")
        ec.toggle_bookmark(self.editor)
        ec.toggle_bookmark(self.editor)
        self.assertEqual(self.editor.markerGet(0) & (1 << ec.MARKNUM_BOOKMARK), 0)

    def test_fold_jumps(self):
        self.set_text("class A:\n  def f():\n    pass\n  def g():\n    pass\n")
        base, header = ec.FOLDLEVELBASE, ec.FOLDLEVELHEADERFLAG
        levels = [base | header, (base + 1) | header, base + 2, (base + 1) | header, base + 2, base]
        for line, level in enumerate(levels):
            self.editor.setFoldLevel(line, level)
        self.editor.gotoLine(2)
        ec.jump_to_parent_fold(self.editor)
        self.assertEqual(self.editor.lineFromPosition(self.editor.currentPos()), 1)
        ec.jump_to_next_fold(self.editor)
        self.assertEqual(self.editor.lineFromPosition(self.editor.currentPos()), 3)
        ec.jump_to_previous_fold(self.editor)
        self.assertEqual(self.editor.lineFromPosition(self.editor.currentPos()), 1)


class ReflowTestCase(EditorTestCase):
    TEXT = ("This is a long paragraph which is useful in testing reflow\n"
            "and it continues here.\n"
            "\n"
            "Second paragraph stays.\n")

    def setUp(self):
        super().setUp()
        self.editor.setUseTabs(False)
        self.editor.setTabWidth(8)

    def test_caret_reflows_its_paragraph_only(self):
        self.set_text(self.TEXT)
        self.editor.gotoPos(self.TEXT.index("useful"))
        ec.reflow_paragraph(self.editor, 30)
        self.assertEqual(self.text(), (
            "This is a long paragraph which\nis useful in testing reflow\nand it continues here.\n"
            "\nSecond paragraph stays.\n"))
        # Same number of non-whitespace characters before the caret.
        pos = self.editor.currentPos()
        self.assertEqual(self.text()[pos:pos + 6], "useful")

    def test_selection_ending_on_blank_line_stays_in_paragraph(self):
        self.set_text(self.TEXT)
        self.editor.setSel(0, self.TEXT.index("\n\n") + 1)
        ec.reflow_paragraph(self.editor, 80)
        self.assertEqual(self.text(), (
            "This is a long paragraph which is useful in testing reflow and it continues\nhere.\n"
            "\nSecond paragraph stays.\n"))

    def test_comment_prefix_and_tabs(self):
        self.set_text("\t# one two three four five six seven\n")
        self.editor.setUseTabs(True)
        self.editor.gotoPos(1)
        ec.reflow_paragraph(self.editor, 25)
        # The tab counts as 8 columns, so "four" no longer fits.
        self.assertEqual(self.text(), "\t# one two three\n\t# four five six\n\t# seven\n")

    def test_one_undo_step(self):
        self.set_text(self.TEXT)
        ec.reflow_paragraph(self.editor, 30)
        self.editor.undo()
        self.assertEqual(self.text(), self.TEXT)


class KomodoLanguageTestCase(EditorTestCase):
    def test_pygments_names_become_komodo_names(self):
        self.assertEqual(ec.komodo_language_name(["Batchfile", "batch", "bat"]), "Batch")
        self.assertEqual(ec.komodo_language_name(["INI", "ini", "cfg"]), "Ini")
        self.assertIsNone(ec.komodo_language_name(["NotALanguage"]))
        self.editor.set_lexer_for_filename("x.bat")
        self.assertEqual(self.editor.language_name(), "Batch")

    def test_batch_styles_like_komodo(self):
        from qtedit.editor import BATCH_COMMENT_STYLE, BATCH_LABEL_STYLE, BATCH_OPERATOR_STYLE, \
            BATCH_WORD_STYLE, batch_pieces
        styled = [(text, style) for text, style in batch_pieces(
            "@echo on\nREM x=1\nc:\n:label\n:: note\nset A=1\n") if text.strip()]
        self.assertIn(("REM x=1", BATCH_COMMENT_STYLE), styled)
        self.assertIn(("c:", BATCH_WORD_STYLE), styled)  # drive change
        self.assertIn((":label", BATCH_LABEL_STYLE), styled)
        self.assertIn((":: note", BATCH_COMMENT_STYLE), styled)
        self.assertIn(("=", BATCH_OPERATOR_STYLE), styled)
        # No keyword list in Komodo's Batch language: echo/set stay default.
        self.assertNotIn(BATCH_WORD_STYLE, [s for t, s in styled if t in ("e", "s")])
