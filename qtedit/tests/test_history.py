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
