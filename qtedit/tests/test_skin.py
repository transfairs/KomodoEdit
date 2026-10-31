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
        # Classic statusbar: 30px including its 1px top border.
        self.assertRegex(qss, r"QStatusBar \{[^}]*min-height: 29px")
        # Tab strip 32px = 2px padding top/bottom + 2px underline + 26px.
        self.assertRegex(qss, r'QTabBar\[koTabs="true"\]::tab \{[^}]*min-height: 26px')
        # 1.6rem menubar at a 14.67px rem is Gecko's 23px, not 24.
        self.assertIn("padding: 2px 6px 3px", build_qss(rem_px=11 * 96 / 72, line_px=18))
        self.assertIn("border-bottom: 2px solid #3f8aff", qss)  # selected tab


class FileIconTestCase(unittest.TestCase):
    def test_random_color_matches_komodo(self):
        import doctest
        from qtedit import random_color
        self.assertEqual(doctest.testmod(random_color).failed, 0)
        # Checked against Komodo's randomColor.js run in SpiderMonkey (gjs);
        # V8 gives different results for long names like these.
        self.assertEqual(random_color.random_color("Batch", luminosity="dark"), "#6a840a")
        self.assertEqual(random_color.random_color("ActionScript", luminosity="light"), "#b485f7")
        self.assertEqual(random_color.random_color("TemplateToolkit", luminosity="light"), "#fc79bf")

    def test_generated_icon_uses_the_language_colour(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        if QApplication.instance() is None:
            self.app = QApplication([])
        from qtedit.statusbar import file_icon
        image = file_icon("Batch").pixmap(14, 14).toImage()
        colors = {image.pixelColor(x, y).name() for x in range(14) for y in range(14)
                  if image.pixelColor(x, y).alpha() == 255}
        self.assertEqual(colors, {"#6a840a"})  # as in the Komodo 12.10 screenshot
