import os
import tempfile
import unittest

from qtedit.skin.css import Stylesheet, komodo_stylesheet, load_colors
from qtedit.skin.qss import build_qss


def _sheet(text):
    with tempfile.NamedTemporaryFile("w", suffix=".css", delete=False) as f:
        f.write(text)
    try:
        return Stylesheet([f.name])
    finally:
        os.unlink(f.name)


class StylesheetTestCase(unittest.TestCase):
    def test_selector_lists_are_split_and_normalized(self):
        sheet = _sheet("a b,\n  c   >  d { color: red; }")
        self.assertEqual(sheet.value("a b", "color"), "red")
        self.assertEqual(sheet.value("c > d", "color"), "red")

    def test_later_rule_wins_unless_earlier_is_important(self):
        sheet = _sheet(
            "x { color: red !important; width: 1px; }\n"
            "x { color: blue; width: 2px; }"
        )
        self.assertEqual(sheet.value("x", "color"), "red")
        self.assertEqual(sheet.value("x", "width"), "2px")

    def test_statement_at_rules_do_not_swallow_the_next_rule(self):
        sheet = _sheet('@namespace url("http://example.org/xul");\nx { color: red; }')
        self.assertEqual(sheet.value("x", "color"), "red")

    def test_at_rule_blocks_are_skipped(self):
        sheet = _sheet(
            "@media all { x { color: red; } }\n"
            "/* x { color: green; } */\n"
            "x { color: blue; }"
        )
        self.assertEqual(sheet.rule("x"), {"color": "blue"})


class KomodoSnapshotTestCase(unittest.TestCase):
    def test_snapshot_has_komodo_statusbar_values(self):
        sheet = komodo_stylesheet()
        self.assertEqual(sheet.value("#komodo_main statusbar", "height"), "28px")
        self.assertEqual(load_colors()["background"], "#2c2c33")

    def test_qss_carries_komodo_values(self):
        qss = build_qss(rem_px=15, line_px=17)
        self.assertIn("#326ecd", qss)  # menubar toolbaritem
        self.assertIn("min-height: 28px", qss)  # statusbar
        self.assertIn("border-bottom: 2px solid #3f8aff", qss)  # selected tab
