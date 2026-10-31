import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

from qtedit import mru  # noqa: E402
from qtedit.prefs import DEFAULT_PREFS, PrefSet  # noqa: E402

_app = QApplication.instance() or QApplication([])


class MruTestCase(unittest.TestCase):
    def setUp(self):
        # Never the global (on-disk) prefs.
        self.prefs = PrefSet()
        for name, value in DEFAULT_PREFS.items():
            self.prefs.set(name, value)
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = []
        for i in range(8):
            path = os.path.join(self.tmp.name, f"p{i}.komodoproject")
            open(path, "w").close()
            self.paths.append(path)
        self.menu = QMenu()

    def tearDown(self):
        self.menu.deleteLater()
        _app.processEvents()
        self.tmp.cleanup()

    def labels(self, menu):
        return [a.text() for a in menu.actions() if not a.isSeparator()]

    def test_add_moves_to_top_and_trims(self):
        self.prefs.set("mruFileSize", 3)
        for path in ("a", "b", "c", "a", "d"):
            mru.add(self.prefs, mru.FILE_LIST, path)
        self.assertEqual(mru.entries(self.prefs, mru.FILE_LIST), ["d", "a", "c"])

    def test_empty_menu(self):
        mru.fill_menu(self.menu, self.prefs, mru.FILE_LIST, print)
        self.assertEqual(self.labels(self.menu), ["No Recent Files"])
        self.assertFalse(self.menu.actions()[0].isEnabled())

    def test_projects_menu_limit_more_and_missing_files(self):
        os.unlink(self.paths[0])
        for path in reversed(self.paths):
            mru.add(self.prefs, mru.PROJECT_LIST, path)
        opened = []
        mru.fill_menu(self.menu, self.prefs, mru.PROJECT_LIST, opened.append, limit=5,
                      manage=("&Manage the Most Recent Projects List", None))
        labels = self.labels(self.menu)
        self.assertEqual(labels[:5], ["&1 p1", "&2 p2", "&3 p3", "&4 p4", "&5 p5"])
        self.assertEqual(labels[5:], ["&More", "&Manage the Most Recent Projects List"])
        more = self.menu.actions()[5].menu()
        self.assertEqual(self.labels(more), ["&1 p6", "&2 p7"])
        self.menu.actions()[0].trigger()
        self.assertEqual(opened, [self.paths[1]])
        self.assertNotIn(self.paths[0], mru.entries(self.prefs, mru.PROJECT_LIST))

    def test_closed_tabs_stack(self):
        tabs = mru.ClosedTabs()
        tabs.fill_menu(self.menu, print)
        self.assertEqual(self.labels(self.menu), ["No tabs to reopen"])
        for path in ("/x/a.py", "/x/b.py", "/x/a.py"):
            tabs.note(path)
        self.menu.clear()
        tabs.fill_menu(self.menu, print, "Ctrl+Shift+T")
        self.assertEqual(self.labels(self.menu), ["&1 a.py\tCtrl+Shift+T", "&2 b.py"])
        self.assertEqual(tabs.pop(), "/x/a.py")
