"""Expected outputs copied from the doctests of Komodo's
src/python-sitelib/reflow.py."""
import doctest
import unittest

from qtedit import reflow as reflow_module
from qtedit.reflow import Paragraphize, reflow


class DoctestTestCase(unittest.TestCase):
    def test_module_doctests(self):
        result = doctest.testmod(reflow_module)
        self.assertGreater(result.attempted, 0)
        self.assertEqual(result.failed, 0)


class KomodoExamplesTestCase(unittest.TestCase):
    def test_blank_lines_and_trailing_space_survive(self):
        self.assertEqual(reflow("tomato\n\nbar\n\nasdas\n", 30, "\n"), "tomato\n\nbar\n\nasdas\n")
        self.assertEqual(reflow("tomato\n\nbar\n\nasdas ", 30, "\n"), "tomato\n\nbar\n\nasdas ")

    def test_crlf_dialogue(self):
        tst = ("  Susan: I assume that would push out our release date, though, right?\r\n\r\n"
               "  Tom: What? No, no, absolutely not. In fact, I've been building a prototype just to "
               "get a feel for it, and I'm pretty sure that we could have an alpha out earlier than "
               "what we've currently got planned.\r\n\r\n  Susan: Why earlier?")
        self.assertEqual(reflow(tst, 40, "\n"), (
            "  Susan: I assume that would push out\n  our release date, though, right?\n\r\n"
            "  Tom: What? No, no, absolutely not. In\n  fact, I've been building a prototype\n"
            "  just to get a feel for it, and I'm\n  pretty sure that we could have an\n"
            "  alpha out earlier than what we've\n  currently got planned.\n\r\n  Susan: Why earlier?"))

    def test_bulleted_comment(self):
        tst = ("# - get PySQLite into our silo'd Python and make it easy for dev builders\n"
               "#   on all platforms\n"
               "# - what mechanism to use to change code browser fileset?\n"
               "# - What about cleaning out info from the DB for deleted files?\n"
               "#   Perhaps that can be done lazily when looking up symbols? I.e.\n"
               "#   when about to report a symbol that comes from a file, check\n"
               "#   that that file still exists. That might be too slow. Perhaps\n"
               "#   the logic could be: check that the file still exists if we ...")
        self.assertEqual(len(Paragraphize(tst)), 3)
        self.assertEqual(reflow(tst, 40, "\n"), (
            "# - get PySQLite into our silo'd Python\n#   and make it easy for dev builders on\n"
            "#   all platforms\n# - what mechanism to use to change code\n#   browser fileset?\n"
            "# - What about cleaning out info from\n#   the DB for deleted files? Perhaps\n"
            "#   that can be done lazily when looking\n#   up symbols? I.e. when about to\n"
            "#   report a symbol that comes from a\n#   file, check that that file still\n"
            "#   exists. That might be too slow.\n#   Perhaps the logic could be: check\n"
            "#   that the file still exists if we ..."))

    def test_tabs_and_bullets(self):
        tst = ("Given a text, return 1 or more paragraph objects, where\na paragraph is defined for "
               "'reflow' purposes, thus:\n\t  - a line consisting only of whitespace is its own\n"
               "\t    paragraph and is a marker of a paragraph end.\n  - a line starting with a "
               "'bullet' is a paragraph beginning.\n")
        self.assertEqual(reflow(tst, 30, "\n"), (
            "Given a text, return 1 or more\nparagraph objects, where a\nparagraph is defined for\n"
            "'reflow' purposes, thus:\n          - a line consisting\n            only of whitespace\n"
            "            is its own\n            paragraph and is a\n            marker of a\n"
            "            paragraph end.\n  - a line starting with a\n    'bullet' is a paragraph\n"
            "    beginning.\n"))

    def test_greek_text(self):
        homer = ("The other instances in Homer of double names in the language of men and gods are "
                 "2.813 τὴν ἦ τοι ἄνδρες "
                 "Βατ end!")
        self.assertEqual(reflow(homer, 20, "\n"), (
            "The other instances\nin Homer of double\nnames in the\nlanguage of men and\n"
            "gods are 2.813 τὴν ἦ\nτοι "
            "ἄνδρες Βατ end!"))
