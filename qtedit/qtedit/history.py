"""Navigation > Back/Forward (Alt+Left/Right), ported from Komodo.

- HistorySession: the back/forward stacks of src/history/editorhistory.py
  (note_loc, go_back, go_forward) with koHistory.py's "same line as the
  previous location" filter.
- Database: Komodo's history.sqlite (same tables). Every noted location is
  a history_visit row whose referer_id points at the one before it, so the
  back history is a linked list. On shutdown only the stack position is
  saved (meta top_loc_id and num_forward_visits); the next start walks the
  list from there. As in Komodo, visits are always recorded, but only
  reloaded when the "Restore Tab History" pref (workspace_restory_history)
  is on, and the newest 500 visits are kept.
- EditorHistory: when locations get noted, from library/history.js and
  views-editor.p.xml: after the caret settles (200ms debounce) more than 5
  lines away, deferred until the next note, and for the old view when the
  current view changes. Moving through the history doesn't note itself.
"""
import os
import sqlite3
from collections import deque

from PySide6.QtCore import QObject, QStandardPaths, QTimer, Signal

# views-buffer.p.xml _onUpdateUI debounce, views-editor.p.xml line jump.
UPDATE_UI_DEBOUNCE_MS = 200
LINE_JUMP = 5
# editorhistory.py HistorySession / Database limits.
RECENT_BACK_VISITS_CACHE_LENGTH = 100
RECENT_BACK_VISITS_DEPLETION_LENGTH = 12
URIS_TO_KEEP = 500
SC_UPDATE_SELECTION = 0x2
RESTORE_PREF = "workspace_restory_history"  # sic, Komodo's pref name
# history.js uses the window number; qtedit has one window.
SESSION_NAME = "1"

# editorhistory.py _g_database_schema, minus columns only Komodo's view
# system fills (marker handles, tab groups, awesome-bar content).
_SCHEMA = """
    CREATE TABLE IF NOT EXISTS history_meta (
        key TEXT UNIQUE ON CONFLICT REPLACE,
        value TEXT
    );
    CREATE TABLE IF NOT EXISTS history_uri (
        id INTEGER NOT NULL PRIMARY KEY,
        is_obsolete INTEGER DEFAULT 0,
        uri TEXT UNIQUE
    );
    CREATE TABLE IF NOT EXISTS history_visit (
        id INTEGER NOT NULL PRIMARY KEY,
        is_obsolete INTEGER DEFAULT 0,
        referer_id INTEGER,
        timestamp REAL,
        session_name TEXT DEFAULT NULL,
        uri_id INTEGER,
        line INTEGER,
        col INTEGER
    );
    CREATE INDEX IF NOT EXISTS history_visit_uri_id ON history_visit(uri_id);
    CREATE TRIGGER IF NOT EXISTS history_visit_set_timestamp AFTER INSERT ON history_visit
    BEGIN
        UPDATE history_visit SET timestamp = julianday('now') WHERE rowid = new.rowid;
    END;
"""


def default_db_path():
    """koHistory.py: $USERDATADIR/history.sqlite."""
    data_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "history.sqlite")


class Location:
    """`key` identifies the buffer: the file path, or the editor itself
    for untitled buffers. `uri` is what the database stores; untitled
    buffers get a kotemporary:// URI like in Komodo, which can't be
    reopened after a restart."""

    def __init__(self, key, line, col, uri=None, id=None, referer_id=None):
        self.key = key
        self.line = line
        self.col = col
        self.uri = uri if uri is not None else (key if isinstance(key, str) else
                                                f"kotemporary://{id_of(key)}/untitled")
        self.id = id
        self.referer_id = referer_id

    def __eq__(self, other):
        return (isinstance(other, Location) and self.key == other.key
                and self.line == other.line and self.col == other.col)

    def __repr__(self):
        return f"<Location {self.key}#{self.line},{self.col}>"


def id_of(obj):
    return f"{id(obj):x}"


class Database:
    """Write-through, unlike Komodo's in-memory copy that is flushed on
    shutdown: a crash keeps the history and the write rate is tiny."""

    def __init__(self, path):
        self.path = path
        try:
            self.cx = self._open()
        except sqlite3.DatabaseError:
            # Bug 101551: recover from a corrupted database
            os.replace(path, path + ".bak")
            self.cx = self._open()

    def _open(self):
        cx = sqlite3.connect(self.path)
        cx.executescript(_SCHEMA)
        cx.commit()
        return cx

    def close(self):
        self.cx.close()

    def get_meta(self, key, default=None):
        row = self.cx.execute("SELECT value FROM history_meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_meta(self, key, value):
        self.cx.execute("INSERT INTO history_meta(key, value) VALUES (?, ?)", (key, value))
        self.cx.commit()

    def uri_id_from_uri(self, uri):
        """Creates the row if new and revives an obsoleted one."""
        row = self.cx.execute("SELECT id, is_obsolete FROM history_uri WHERE uri=?", (uri,)).fetchone()
        if row is None:
            return self.cx.execute("INSERT INTO history_uri(uri) VALUES (?)", (uri,)).lastrowid
        if row[1]:
            self.cx.execute("UPDATE history_uri SET is_obsolete=0 WHERE id=?", (row[0],))
        return row[0]

    def add_loc(self, loc, referer_id):
        uri_id = self.uri_id_from_uri(loc.uri)
        loc.id = self.cx.execute(
            "INSERT INTO history_visit(referer_id, uri_id, line, col, session_name)"
            " VALUES (?, ?, ?, ?, ?)",
            (referer_id, uri_id, loc.line, loc.col, SESSION_NAME)).lastrowid
        loc.referer_id = referer_id
        self.cx.commit()
        return loc

    def update_referer_id(self, loc, referer_id):
        loc.referer_id = referer_id
        self.cx.execute("UPDATE history_visit SET referer_id=? WHERE id=?", (referer_id, loc.id))
        self.cx.commit()

    def obsolete_uri(self, uri):
        row = self.cx.execute("SELECT id FROM history_uri WHERE uri=?", (uri,)).fetchone()
        if row is not None:
            self.cx.execute("UPDATE history_visit SET is_obsolete=1 WHERE uri_id=?", (row[0],))
            self.cx.execute("UPDATE history_uri SET is_obsolete=1 WHERE id=?", (row[0],))
            self.cx.commit()

    def visit(self, visit_id):
        """(Location, is_obsolete) for an id, or for the session's latest
        visit if visit_id is None; None if there is no such row (expired)."""
        query = ("SELECT v.id, v.referer_id, v.line, v.col, v.is_obsolete, u.uri"
                 " FROM history_visit v JOIN history_uri u ON u.id = v.uri_id")
        if visit_id is None:
            row = self.cx.execute(query + " WHERE v.session_name=? ORDER BY v.id DESC LIMIT 1",
                                  (SESSION_NAME,)).fetchone()
        else:
            row = self.cx.execute(query + " WHERE v.id=?", (visit_id,)).fetchone()
        if row is None:
            return None
        id_, referer_id, line, col, is_obsolete, uri = row
        # A kotemporary:// key never matches a buffer, so it gets skipped.
        return Location(uri, line, col, uri=uri, id=id_, referer_id=referer_id), bool(is_obsolete)

    def expire(self):
        """_write_db_to_disk: keep the newest URIS_TO_KEEP visits."""
        row = self.cx.execute("SELECT id FROM history_visit ORDER BY id DESC LIMIT 1 OFFSET ?",
                              (URIS_TO_KEEP,)).fetchone()
        if row is not None:
            self.cx.execute("DELETE FROM history_visit WHERE id <= ?", (row[0],))
            self.cx.execute("DELETE FROM history_uri WHERE id NOT IN"
                            " (SELECT DISTINCT uri_id FROM history_visit)")
            self.cx.commit()


class HistorySession:
    def __init__(self, db=None):
        # Newest first in both: recent_back_visits[0] is the next go_back,
        # forward_visits[-1] the next go_forward.
        self.db = db
        self.recent_back_visits = deque(maxlen=RECENT_BACK_VISITS_CACHE_LENGTH)
        self.forward_visits = deque()
        self._last_visit = None

    # -- persistence (HistorySession.load/save) --

    def _walk(self, visit_id, count):
        """Up to `count` non-obsolete visits following referer_id links,
        relinking across obsolete ones like _load_recent_history_cache."""
        locs = []
        sentinel = 1000  # sanity check for huge block of obsoleted locs
        while len(locs) < count and sentinel > 0:
            found = self.db.visit(visit_id)
            if found is None:
                break
            loc, is_obsolete = found
            if is_obsolete:
                sentinel -= 1
            else:
                sentinel = 1000
                if locs:
                    locs[-1].referer_id = loc.id
                locs.append(loc)
            visit_id = loc.referer_id
            if visit_id is None:
                break
        if locs and len(locs) < count:
            locs[-1].referer_id = None
        return locs

    def load(self):
        """num_forward_visits == -1 means the last run didn't save (crash):
        then start from the latest visit with no forward history."""
        num_forward = int(self.db.get_meta(f"{SESSION_NAME}:num_forward_visits", -1))
        top_loc_id = None
        if num_forward != -1:
            self.db.set_meta(f"{SESSION_NAME}:num_forward_visits", -1)
            top = self.db.get_meta(f"{SESSION_NAME}:top_loc_id")
            top_loc_id = int(top) if top not in (None, "None") else None
            if top_loc_id is None:
                return
        else:
            num_forward = 0
        locs = self._walk(top_loc_id, num_forward + 1 + RECENT_BACK_VISITS_CACHE_LENGTH)
        self.forward_visits.extend(locs[:num_forward])
        if len(locs) > num_forward:
            self._last_visit = locs[num_forward]
            self.recent_back_visits.extend(locs[num_forward + 1:])

    def save(self):
        self.db.set_meta(f"{SESSION_NAME}:num_forward_visits", str(len(self.forward_visits)))
        if self.forward_visits:
            top = self.forward_visits[0].id
        elif self.recent_back_visits:
            top = self.recent_back_visits[0].id
        else:
            top = None
        self.db.set_meta(f"{SESSION_NAME}:top_loc_id", str(top))

    def _replenish(self):
        """_replenish_recent_back_visits: refill the cache from the db."""
        oldest = self.recent_back_visits[-1]
        if oldest.referer_id is None:
            return
        room = RECENT_BACK_VISITS_CACHE_LENGTH - len(self.recent_back_visits)
        more = self._walk(oldest.referer_id, room)
        if more:
            if oldest.referer_id != more[0].id:
                self.db.update_referer_id(oldest, more[0].id)
            self.recent_back_visits.extend(more)
        else:
            oldest.referer_id = None

    # -- the stacks --

    def note_loc(self, loc):
        # editorhistory.py's TODO: "This needs to a be a no-op if the
        # location to note is the exact same location as we just jumped
        # to". Without it the landing spot of Back, noted after the caret
        # jump, wipes the forward history.
        last = self._last_visit
        if last is not None and last.key == loc.key and last.line == loc.line:
            return None
        if self.recent_back_visits:
            prev = self.recent_back_visits[0]
            if prev.key == loc.key and prev.line == loc.line:
                return None
        if self.db is not None:
            referer_id = self.recent_back_visits[0].id if self.recent_back_visits else None
            self.db.add_loc(loc, referer_id)
        self.recent_back_visits.appendleft(loc)
        self.forward_visits.clear()
        return loc

    def can_go_back(self):
        return len(self.recent_back_visits) > 0

    def can_go_forward(self):
        return len(self.forward_visits) > 0

    def _record_current(self, curr_loc, referer_id):
        """The user moved since the last jump: the current location joins
        the history, linked in front of the newest forward visit."""
        if self.db is not None:
            self.db.add_loc(curr_loc, referer_id)
            if self.forward_visits:
                self.db.update_referer_id(self.forward_visits[-1], curr_loc.id)
        return curr_loc

    def go_back(self, curr_loc, n=1):
        if self.db is not None and (
                n > len(self.recent_back_visits)
                or len(self.recent_back_visits) <= RECENT_BACK_VISITS_DEPLETION_LENGTH):
            self._replenish()
        if n > len(self.recent_back_visits):
            raise IndexError("not enough back history")
        if curr_loc is not None:
            # Reuse the location we jumped to unless the user moved since.
            if curr_loc == self._last_visit:
                loc = self._last_visit
            else:
                loc = self._record_current(curr_loc, self.recent_back_visits[0].id)
            self.forward_visits.append(loc)
        for _ in range(n - 1):
            self.forward_visits.append(self.recent_back_visits.popleft())
        self._last_visit = self.recent_back_visits.popleft()
        return self._last_visit

    def go_forward(self, curr_loc, n=1):
        if n > len(self.forward_visits):
            raise IndexError("not enough forward history")
        if curr_loc is not None:
            if curr_loc == self._last_visit:
                loc = self._last_visit
            else:
                referer_id = self.recent_back_visits[0].id if self.recent_back_visits else None
                loc = self._record_current(curr_loc, referer_id)
            self.recent_back_visits.appendleft(loc)
        for _ in range(n - 1):
            self.recent_back_visits.appendleft(self.forward_visits.pop())
        self._last_visit = self.forward_visits.pop()
        return self._last_visit

    def forget(self, key):
        """Drop a buffer's locations once it can't be reopened (Komodo's
        obsolete_uri)."""
        for stack in (self.recent_back_visits, self.forward_visits):
            gone = [loc for loc in stack if loc.key == key]
            kept = [loc for loc in stack if loc.key != key]
            stack.clear()
            stack.extend(kept)
            if self.db is not None:
                for uri in {loc.uri for loc in gone}:
                    self.db.obsolete_uri(uri)


def editor_key(editor):
    return os.path.abspath(editor.filepath) if editor.filepath else editor


def location_of(editor):
    pos = editor.currentPos()
    return Location(editor_key(editor), editor.lineFromPosition(pos), editor.column(pos))


class EditorHistory(QObject):
    """open_location(loc) -> editor or None is supplied by the window: it
    activates (or opens) the buffer for loc.key."""

    message = Signal(str)  # views.properties historyCouldntMove*

    def __init__(self, open_location, db_path=None, restore=False, parent=None):
        """db_path None keeps the history in memory only (tests)."""
        super().__init__(parent)
        self._db = Database(db_path) if db_path else None
        self.session = HistorySession(self._db)
        if self._db is not None and restore:
            self.session.load()
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

    def close(self):
        """Shutdown: commit the pending location, save the stack position,
        expire old visits."""
        self._flush_deferred()
        if self._db is not None:
            self.session.save()
            self._db.expire()
            self._db.close()
            self._db = self.session.db = None

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
        # The pending caret-jump note is where we are now, which `curr`
        # records; flushing it later (history.js does, at the next note or
        # on view close) would note it again and wipe the forward history.
        self._deferred = None
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
