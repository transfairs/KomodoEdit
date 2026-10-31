import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from qtedit.editor import CodeEditor  # noqa: E402
from qtedit.history import EditorHistory, HistorySession, Location  # noqa: E402

_app = QApplication.instance() or QApplication([])


class HistorySessionTestCase(unittest.TestCase):
    def test_back_and_forward(self):
        session = HistorySession()
        for line in (1, 20, 40):
            session.note_loc(Location("a", line, 0))
        here = Location("a", 60, 0)
        self.assertEqual(session.go_back(here).line, 40)
        self.assertEqual(session.go_back(Location("a", 40, 0)).line, 20)
        self.assertEqual(session.go_forward(Location("a", 20, 0)).line, 40)
        self.assertEqual(session.go_forward(Location("a", 40, 0)), here)
        self.assertFalse(session.can_go_forward())

    def test_same_line_is_not_noted_twice(self):
        session = HistorySession()
        session.note_loc(Location("a", 3, 0))
        self.assertIsNone(session.note_loc(Location("a", 3, 7)))
        self.assertEqual(len(session.recent_back_visits), 1)

    def test_noting_clears_forward(self):
        session = HistorySession()
        session.note_loc(Location("a", 1, 0))
        session.go_back(Location("a", 30, 0))
        session.note_loc(Location("a", 50, 0))
        self.assertFalse(session.can_go_forward())


class EditorHistoryTestCase(unittest.TestCase):
    def setUp(self):
        self.editors = [CodeEditor(), CodeEditor()]
        for i, editor in enumerate(self.editors):
            editor.filepath = f"/tmp/file{i}"
            editor.setText("\n" * 100)
        self.current = self.editors[0]
        self.history = EditorHistory(self.open_location)
        self.messages = []
        self.history.message.connect(self.messages.append)

    def tearDown(self):
        for editor in self.editors:
            editor.deleteLater()
        _app.processEvents()

    def open_location(self, loc):
        for editor in self.editors:
            if editor.filepath == loc.key:
                self.switch(editor)
                return editor
        return None

    def switch(self, editor):
        self.current = editor
        self.history.view_changed(editor)

    def line(self):
        return self.current.lineFromPosition(self.current.currentPos())

    def test_view_change_notes_the_old_view_and_back_returns(self):
        self.switch(self.editors[0])
        self.editors[0].gotoLine(10)
        self.switch(self.editors[1])
        self.history.go_back(self.current)
        self.assertIs(self.current, self.editors[0])
        self.assertEqual(self.line(), 10)
        self.history.go_forward(self.current)
        self.assertIs(self.current, self.editors[1])

    def test_deferred_jump_is_noted_by_the_next_note(self):
        editor = self.editors[0]
        self.switch(editor)
        editor.gotoLine(50)
        self.history.note_unless_history_move(editor, defer=True)
        self.assertFalse(self.history.can_go_back())
        editor.gotoLine(80)
        self.history.note_unless_history_move(editor, defer=True)
        self.history.go_back(editor)
        self.assertEqual(self.line(), 50)

    def test_closed_buffer_is_skipped(self):
        self.switch(self.editors[0])
        self.switch(self.editors[1])
        self.editors[0].filepath = "/tmp/gone"
        self.history.go_back(self.current)
        self.assertIn("Could not move back", self.messages[0])


class PersistenceTestCase(unittest.TestCase):
    """Restarts simulated with a temp history.sqlite, never the real one."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "history.sqlite")

    def tearDown(self):
        self.tmp.cleanup()

    def session(self):
        from qtedit.history import Database
        session = HistorySession(Database(self.path))
        session.load()
        return session

    def close(self, session):
        session.save()
        session.db.expire()
        session.db.close()

    def test_back_and_forward_survive_a_restart(self):
        first = self.session()
        for line in (10, 30, 50, 70):
            first.note_loc(Location("/a.py", line, 0))
        first.go_back(Location("/a.py", 90, 0))       # at 70, 90 forward
        first.go_back(Location("/a.py", 70, 0))       # at 50, 70 + 90 forward
        self.close(first)

        second = self.session()
        self.assertEqual([loc.line for loc in second.forward_visits], [90, 70])
        self.assertEqual(second.go_back(Location("/a.py", 50, 0)).line, 30)
        self.assertEqual(second.go_forward(Location("/a.py", 30, 0)).line, 50)
        self.assertEqual(second.go_forward(Location("/a.py", 50, 0)).line, 70)

    def test_crash_restarts_from_latest_visit(self):
        first = self.session()
        for line in (10, 30, 50):
            first.note_loc(Location("/a.py", line, 0))
        first.db.close()  # no save(): num_forward_visits stays unknown
        second = self.session()
        # Like Komodo, the latest visit becomes "where you are".
        self.assertEqual(second.go_back(Location("/a.py", 80, 0)).line, 30)

    def test_obsolete_uri_is_skipped_on_load(self):
        first = self.session()
        for key in ("/a.py", "/gone.py", "/a.py"):
            first.note_loc(Location(key, len(first.recent_back_visits) * 20, 0))
        first.note_loc(Location("/b.py", 1, 0))
        first.forget("/gone.py")
        self.close(first)
        second = self.session()
        self.assertEqual([loc.key for loc in second.recent_back_visits], ["/a.py", "/a.py"])

    def test_untitled_buffers_never_match_after_restart(self):
        first = self.session()
        first.note_loc(Location(object(), 5, 0))
        first.note_loc(Location("/a.py", 1, 0))
        first.note_loc(Location("/a.py", 30, 0))
        self.close(first)
        second = self.session()
        self.assertTrue(second.recent_back_visits[-1].key.startswith("kotemporary://"))

    def test_expiry_keeps_newest_visits(self):
        from qtedit import history
        first = self.session()
        for line in range(history.URIS_TO_KEEP + 20):
            first.note_loc(Location(f"/f{line % 3}.py", line, 0))
        self.close(first)
        import sqlite3
        cx = sqlite3.connect(self.path)
        self.assertEqual(cx.execute("SELECT count(*) FROM history_visit").fetchone()[0], history.URIS_TO_KEEP)
        cx.close()


class JumpTargetTestCase(unittest.TestCase):
    def test_noting_the_back_target_keeps_forward(self):
        session = HistorySession()
        session.note_loc(Location("a", 10, 0))
        session.go_back(Location("a", 50, 0))
        session.note_loc(Location("a", 10, 4))  # the caret-jump note after Back
        self.assertTrue(session.can_go_forward())


class DeferredAcrossMoveTestCase(EditorHistoryTestCase):
    def test_pending_note_does_not_wipe_forward(self):
        editor = self.editors[0]
        self.switch(editor)
        editor.gotoLine(30)
        self.history.note_unless_history_move(editor, defer=True)
        editor.gotoLine(70)
        self.history.note_unless_history_move(editor, defer=True)  # pending: 70
        self.history.go_back(editor)
        self.history.close()  # flushes whatever is pending
        self.assertTrue(self.history.can_go_forward())
