"""Navigation > Back/Forward (Alt+Left/Right), ported from Komodo.

- HistorySession: the back/forward stacks of src/history/editorhistory.py
  (note_loc, go_back, go_forward) with koHistory.py's "same line as the
  previous location" filter. Komodo keeps them in an SQLite database across
  restarts; here they live in memory for the session.
- EditorHistory: when locations get noted, from library/history.js and
  views-editor.p.xml: after the caret settles (200ms debounce) more than 5
  lines away, deferred until the next note, and for the old view when the
  current view changes. Moving through the history doesn't note itself.
"""
from collections import deque

from PySide6.QtCore import QObject, QTimer, Signal

# views-buffer.p.xml _onUpdateUI debounce, views-editor.p.xml line jump.
UPDATE_UI_DEBOUNCE_MS = 200
LINE_JUMP = 5
# editorhistory.py RECENT_BACK_VISITS_CACHE_LENGTH: max steps per jump.
MAX_BACK_VISITS = 100
SC_UPDATE_SELECTION = 0x2


class Location:
    """`key` identifies the buffer: the file path, or the editor itself
    for untitled buffers (Komodo's kotemporary:// URIs)."""

    def __init__(self, key, line, col):
        self.key = key
        self.line = line
        self.col = col

    def __eq__(self, other):
        return (isinstance(other, Location) and self.key == other.key
                and self.line == other.line and self.col == other.col)

    def __repr__(self):
        return f"<Location {self.key}#{self.line},{self.col}>"


class HistorySession:
    def __init__(self):
        # Newest first in both: recent_back_visits[0] is the next go_back,
        # forward_visits[-1] the next go_forward.
        self.recent_back_visits = deque(maxlen=MAX_BACK_VISITS)
        self.forward_visits = deque()
        self._last_visit = None

    def note_loc(self, loc):
        if self.recent_back_visits:
            prev = self.recent_back_visits[0]
            if prev.key == loc.key and prev.line == loc.line:
                return None
        self.recent_back_visits.appendleft(loc)
        self.forward_visits.clear()
        return loc

    def can_go_back(self):
        return len(self.recent_back_visits) > 0

    def can_go_forward(self):
        return len(self.forward_visits) > 0

    def go_back(self, curr_loc, n=1):
        if n > len(self.recent_back_visits):
            raise IndexError("not enough back history")
        if curr_loc is not None:
            # Reuse the location we jumped to unless the user moved since.
            self.forward_visits.append(self._last_visit if curr_loc == self._last_visit else curr_loc)
        for _ in range(n - 1):
            self.forward_visits.append(self.recent_back_visits.popleft())
        self._last_visit = self.recent_back_visits.popleft()
        return self._last_visit

    def go_forward(self, curr_loc, n=1):
        if n > len(self.forward_visits):
            raise IndexError("not enough forward history")
        if curr_loc is not None:
            self.recent_back_visits.appendleft(
                self._last_visit if curr_loc == self._last_visit else curr_loc)
        for _ in range(n - 1):
            self.recent_back_visits.appendleft(self.forward_visits.pop())
        self._last_visit = self.forward_visits.pop()
        return self._last_visit

    def forget(self, key):
        """Drop a closed untitled buffer's locations (Komodo obsoletes
        them when they can't be reloaded)."""
        for stack in (self.recent_back_visits, self.forward_visits):
            kept = [loc for loc in stack if loc.key != key]
            stack.clear()
            stack.extend(kept)


def editor_key(editor):
    return editor.filepath or editor


def location_of(editor):
    pos = editor.currentPos()
    return Location(editor_key(editor), editor.lineFromPosition(pos), editor.column(pos))


class EditorHistory(QObject):
    """open_location(loc) -> editor or None is supplied by the window: it
    activates (or opens) the buffer for loc.key."""

    message = Signal(str)  # views.properties historyCouldntMove*

    def __init__(self, open_location, parent=None):
        super().__init__(parent)
        self.session = HistorySession()
        self._open_location = open_location
        self._deferred = None
        self._recently_did_history = False
        self._marking = False
        self._last_view = None

    def watch(self, editor):
        editor._history_last_line = 0
        timer = QTimer(editor)
        timer.setSingleShot(True)
        timer.setInterval(UPDATE_UI_DEBOUNCE_MS)
        editor._history_updated = 0

        def on_update_ui(updated):
            editor._history_updated |= updated
            timer.start()

        def debounced():
            updated, editor._history_updated = editor._history_updated, 0
            line = editor.lineFromPosition(editor.currentPos())
            if (not self._marking and updated & SC_UPDATE_SELECTION
                    and abs(line - editor._history_last_line) > LINE_JUMP):
                self.note_unless_history_move(editor, defer=True)
            editor._history_last_line = line

        editor.updateUi.connect(on_update_ui)
        timer.timeout.connect(debounced)

    def note_curr_loc(self, editor, defer=False):
        if editor is None or self._marking:
            return
        self._flush_deferred()
        self._recently_did_history = False
        loc = location_of(editor)
        if defer:
            self._deferred = loc
        else:
            self.session.note_loc(loc)

    def note_unless_history_move(self, editor, defer=False):
        if self._recently_did_history:
            self._recently_did_history = False
            return
        self.note_curr_loc(editor, defer)

    def _flush_deferred(self):
        if self._deferred is not None:
            self.session.note_loc(self._deferred)
            self._deferred = None

    def view_changed(self, editor):
        if self._last_view is not None and self._last_view is not editor:
            self.note_unless_history_move(self._last_view)
        self._last_view = editor

    def view_closing(self, editor):
        self._flush_deferred()
        if self._last_view is editor:
            self._last_view = None
        if not editor.filepath:
            self.session.forget(editor)

    def can_go_back(self):
        return self.session.can_go_back()

    def can_go_forward(self):
        return self.session.can_go_forward()

    def go_back(self, current_editor):
        if self.can_go_back():  # keybindings skip the is-enabled test
            self._move(self.session.go_back, self.can_go_back, current_editor, "back")

    def go_forward(self, current_editor):
        if self.can_go_forward():
            self._move(self.session.go_forward, self.can_go_forward, current_editor, "forward")

    def _move(self, go, can_go, current_editor, direction):
        """history.js _history_move: locations whose buffer is gone are
        dropped and the move continues in the same direction."""
        curr = location_of(current_editor) if current_editor is not None else None
        while True:
            loc = go(curr)
            curr = None  # already on the other stack
            # Consumed by the next note attempt: the view change or the
            # caret jump this move causes, so neither lands in the history.
            self._recently_did_history = True
            editor = self._open_location(loc)
            if editor is not None:
                pos = editor.findColumn(min(loc.line, editor.lineCount() - 1), loc.col)
                editor.setAnchor(pos)
                editor.gotoPos(pos)
                return
            self.session.forget(loc.key)
            if not can_go():
                self.message.emit(
                    f"Could not move {direction}: all remaining locations are obsolete.")
                return
