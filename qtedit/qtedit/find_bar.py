"""Komodo's find frame (find/embedded.p.xul + find2.p.js), shown in
#findReplaceWrap below the editor.

One frame covers what used to be separate find bar and Find in Files
dialog, exactly like Komodo 12: the "Where:" menu switches between the
current document, the selection, open files, a directory tree and the
current project, and the rows/buttons shown follow find2.p.js's
_update_mode_ui(). Option checkboxes are IcoMoon glyphs taken from the
skin CSS (`checkbox#opt-regex .checkbox-spacer-box:before`), with labels
hidden as in find2.css.

In-document searching is Scintilla's own engine (findText/searchInTarget/
replaceTarget[RE]); the "in files" modes use find_in_files.py on a worker
thread (find_in_files_ui.py).
"""
import re

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from pyside6_scintilla import Scintilla

from qtedit import find_in_files as fif
from qtedit import icons
from qtedit.find_in_files_ui import PlanWorker, ReplacePreviewDialog, SearchWorker
from qtedit.skin.css import komodo_stylesheet, load_colors

# "Where:" values, as in embedded.p.xul's #search-in-menu.
SEARCH_DOCUMENT = "document"
SEARCH_SELECTION = "selection"
SEARCH_OPEN_FILES = "open-files"
SEARCH_PROJECT = "curr-project"
SEARCH_FILES = "files"
_IN_FILES = (SEARCH_PROJECT, SEARCH_FILES)

# koIFinder.idl FOC_* order; clicking cycles ignore -> match -> smart.
CASE_IGNORE = "ignore-case"
CASE_MATCH = "match-case"
CASE_SMART = "smart-case"
_NEXT_CASE = {CASE_IGNORE: CASE_MATCH, CASE_MATCH: CASE_SMART, CASE_SMART: CASE_IGNORE}
_CASE_TOOLTIPS = {CASE_IGNORE: "Match case: off", CASE_MATCH: "Match case", CASE_SMART: "Smart case"}

MARK_ALL_INDICATOR = 8


def _glyph_for(selector):
    content = komodo_stylesheet().value(selector, "content")
    return icons.css_glyph(content) if content else "?"


class GlyphCheckBox(QToolButton):
    """A find2 option checkbox: label hidden, the spacer-box glyph shown,
    white when off and the `checkbox[checked]` color when on."""

    def __init__(self, komodo_id, tooltip, parent=None):
        super().__init__(parent)
        self.setObjectName(komodo_id)
        self.setCheckable(True)
        self.setToolTip(tooltip)
        self._glyph = _glyph_for(f"checkbox#{komodo_id} .checkbox-spacer-box:before")
        self.toggled.connect(self._update_icon)
        self._update_icon()

    def _update_icon(self, *_args):
        color = komodo_stylesheet().value("checkbox[checked]", "color") if self.isChecked() else None
        self.setIcon(icons.glyph(self._glyph, 16, QColor(color or load_colors()["icons"])))


class CaseCheckBox(QToolButton):
    """#opt-case: a tri-state glyph, always drawn in the highlight color
    (find2.css `#opt-case { color: ... !important }`)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("opt-case")
        self.value = CASE_IGNORE
        self.clicked.connect(self._advance)
        self._update_icon()

    def _advance(self):
        self.value = _NEXT_CASE[self.value]
        self._update_icon()

    def _update_icon(self):
        glyph = _glyph_for(f'checkbox#opt-case[value="{self.value}"] .checkbox-spacer-box:before')
        color = QColor(komodo_stylesheet().value("#opt-case", "color"))
        self.setIcon(icons.glyph(glyph, 16, color))
        self.setToolTip(_CASE_TOOLTIPS[self.value])


def _glyph_button(komodo_id, tooltip):
    """find2.css's icon-only #find-next-btn/#find-prev-btn."""
    button = QPushButton()
    button.setObjectName(komodo_id)
    button.setToolTip(tooltip)
    button.setIcon(icons.glyph(_glyph_for(f"#{komodo_id}:before"), 16))
    return button


class FindFrame(QWidget):
    closed = Signal()
    message = Signal(str)
    hits_found = Signal(list)  # list[FileHit], for the Find Results widget
    replacements_applied = Signal(list)  # undo record of a files Replace All

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("findReplaceWrap")
        self._editor = None
        self._selection_range = None
        self._thread = None
        self._worker = None
        # Callables provided by the main window for the multi-file modes.
        self.open_files_provider = lambda: []
        self.project_dir_provider = lambda: None
        self.default_dir_provider = lambda: ""

        closer = QWidget()
        closer.setObjectName("find-box-closer")
        closer.setToolTip(
            "Click to close. You can also use ESC to close the find frame while the frame has focus."
        )
        closer.setCursor(Qt.CursorShape.SizeVerCursor)
        closer.mousePressEvent = lambda _event: self.hide_bar()

        # --- find-row
        self._opt_repl = GlyphCheckBox("opt-repl", "Replace")
        self._opt_repl.toggled.connect(self._update_mode_ui)
        self._pattern = QLineEdit()
        self._pattern.setObjectName("pattern")
        self._pattern.textChanged.connect(self._update_buttons_enabled)
        self._pattern.returnPressed.connect(self._default_action)
        self._opt_case = CaseCheckBox()
        self._opt_word = GlyphCheckBox("opt-word", "Match whole words")
        self._opt_multiline = GlyphCheckBox("opt-multiline", "Multiline")
        self._opt_multiline.setEnabled(False)  # multiline patterns: not supported yet
        self._opt_regex = GlyphCheckBox("opt-regex", "Regex")
        find_options = QWidget()
        find_options.setObjectName("find-options")
        options_layout = QHBoxLayout(find_options)
        options_layout.setContentsMargins(0, 0, 0, 0)
        options_layout.setSpacing(0)
        for widget in (self._opt_case, self._opt_word, self._opt_multiline, self._opt_regex):
            options_layout.addWidget(widget)

        self._find_next_btn = _glyph_button("find-next-btn", "Find Next")
        self._find_next_btn.clicked.connect(self.find_next)
        self._find_prev_btn = _glyph_button("find-prev-btn", "Find Previous")
        self._find_prev_btn.clicked.connect(self.find_previous)
        self._find_all_btn = QPushButton("Find All")
        self._find_all_btn.clicked.connect(self.find_all)
        self._mark_all_btn = QPushButton("Mark All")
        self._mark_all_btn.clicked.connect(self.mark_all)

        # --- repl-row
        self._repl_label = QLabel("Replace:")
        self._repl = QLineEdit()
        self._repl.setObjectName("repl")
        self._repl.returnPressed.connect(self._default_action)
        self._replace_btn = QPushButton("Replace")
        self._replace_btn.clicked.connect(self.replace)
        self._replace_all_btn = QPushButton("Replace All")
        self._replace_all_btn.clicked.connect(self.replace_all)

        # --- includes-row
        self._search_in = QComboBox()
        self._search_in.setObjectName("search-in-menu")
        for label, value in (
            ("Current document", SEARCH_DOCUMENT),
            ("Selected text", SEARCH_SELECTION),
            ("Open files", SEARCH_OPEN_FILES),
            ("Current project", SEARCH_PROJECT),
            ("Files", SEARCH_FILES),
        ):
            self._search_in.addItem(label, value)
        self._search_in.currentIndexChanged.connect(self._update_mode_ui)
        self._includes_label = QLabel("Include:")
        self._includes = QLineEdit()
        self._includes.setObjectName("includes")
        self._includes.setMinimumWidth(150)

        # --- dirs-row
        self._dirs_label = QLabel("Directories:")
        self._subdirs = GlyphCheckBox("search-in-subdirs", "Search in sub-directories")
        self._subdirs.setChecked(True)  # prefs: find-searchInSubfolders = 1
        self._dirs = QLineEdit()
        self._dirs.setObjectName("dirs")
        browse_btn = QPushButton("...")
        browse_btn.setObjectName("browse-dirs")
        browse_btn.setToolTip("Edit list of directories to search")
        browse_btn.clicked.connect(self._browse_dirs)
        self._dirs_box = QWidget()
        dirs_layout = QHBoxLayout(self._dirs_box)
        dirs_layout.setContentsMargins(0, 0, 0, 0)
        dirs_layout.addWidget(self._dirs, 1)
        dirs_layout.addWidget(browse_btn)
        self._excludes_label = QLabel("Exclude:")
        self._excludes = QLineEdit()
        self._excludes.setObjectName("excludes")

        # The XUL <grid>: labels | label-options | fields | field-options | buttons
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(2)
        grid.setColumnStretch(2, 10)
        grid.setColumnStretch(3, 1)
        grid.addWidget(QLabel("Find:"), 0, 0)
        grid.addWidget(self._opt_repl, 0, 1)
        grid.addWidget(self._pattern, 0, 2)
        grid.addWidget(find_options, 0, 3)
        find_buttons = QHBoxLayout()
        find_buttons.setSpacing(0)
        for button in (self._find_next_btn, self._find_prev_btn, self._find_all_btn, self._mark_all_btn):
            find_buttons.addWidget(button)
        grid.addLayout(find_buttons, 0, 4)

        grid.addWidget(self._repl_label, 1, 0)
        grid.addWidget(self._repl, 1, 2)
        repl_buttons = QHBoxLayout()
        repl_buttons.setSpacing(0)
        repl_buttons.addWidget(self._replace_btn)
        repl_buttons.addWidget(self._replace_all_btn)
        grid.addLayout(repl_buttons, 1, 4)

        grid.addWidget(QLabel("Where:"), 2, 0)
        grid.addWidget(self._search_in, 2, 2)
        grid.addWidget(self._includes_label, 2, 3, Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self._includes, 2, 4)

        grid.addWidget(self._dirs_label, 3, 0)
        grid.addWidget(self._subdirs, 3, 1)
        grid.addWidget(self._dirs_box, 3, 2)
        grid.addWidget(self._excludes_label, 3, 3, Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self._excludes, 3, 4)

        wrap = QWidget()
        wrap.setObjectName("find-box-wrap")
        wrap.setLayout(grid)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(closer)
        layout.addWidget(wrap)

        self._repl_row = (self._repl_label, self._repl, self._replace_btn, self._replace_all_btn)
        self._dirs_row = (self._dirs_label, self._subdirs, self._dirs_box, self._excludes_label, self._excludes)
        self._update_mode_ui()
        self._update_buttons_enabled()

    # --- public API used by the main window

    def set_editor(self, editor):
        self._editor = editor

    def show_bar(self, replace=False, search_in=None):
        """ko.launch.find()/replace(): preload the pattern from a single-line
        selection, or search within a multi-line one (find2.p.js on_load)."""
        editor = self._editor
        self._selection_range = None
        if editor is not None and editor.selectionStart() != editor.selectionEnd():
            start, end = editor.selectionStart(), editor.selectionEnd()
            selected = bytes(editor.textRange(start, end)).decode("utf-8", errors="replace")
            line = editor.lineFromPosition(start)
            whole_line = (start == editor.positionFromLine(line)
                          and end == editor.lineEndPosition(line))
            if "\n" in selected or whole_line:
                self._selection_range = (start, end)
                search_in = search_in or SEARCH_SELECTION
            else:
                self._pattern.setText(selected)
                self._opt_regex.setChecked(False)
        if search_in is None and self.search_in() == SEARCH_SELECTION:
            search_in = SEARCH_DOCUMENT
        if search_in is not None:
            self._search_in.setCurrentIndex(self._search_in.findData(search_in))
        if search_in in _IN_FILES and not self._dirs.text():
            self._dirs.setText(self.default_dir_provider() or "")
        self._opt_repl.setChecked(replace)
        self.show()
        self._pattern.setFocus()
        self._pattern.selectAll()

    def set_pattern(self, pattern):
        if pattern:
            self._pattern.setText(pattern)
            self._pattern.selectAll()

    def hide_bar(self):
        self.hide()
        self.closed.emit()

    def search_in(self):
        return self._search_in.currentData()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide_bar()
            return
        super().keyPressEvent(event)

    # --- mode handling (find2.p.js update()/_update_mode_ui())

    def _update_mode_ui(self, *_args):
        replace = self._opt_repl.isChecked()
        in_files = self.search_in() in _IN_FILES
        for widget in self._repl_row:
            widget.setVisible(replace)
        for widget in self._dirs_row:
            widget.setVisible(in_files)
        self._includes_label.setVisible(in_files)
        self._includes.setVisible(in_files)
        self._dirs_box.setEnabled(self.search_in() == SEARCH_FILES)
        self._find_next_btn.setVisible(not in_files)
        self._find_prev_btn.setVisible(not in_files)
        self._find_all_btn.setVisible(not replace)
        self._mark_all_btn.setVisible(not in_files or replace)
        self._replace_btn.setVisible(replace and not in_files)
        self._replace_all_btn.setVisible(replace)
        if self.search_in() == SEARCH_PROJECT:
            self._dirs.setText(self.project_dir_provider() or "")

    def _update_buttons_enabled(self, *_args):
        has_pattern = bool(self._pattern.text())
        for button in (self._find_next_btn, self._find_prev_btn, self._find_all_btn,
                       self._mark_all_btn, self._replace_btn, self._replace_all_btn):
            button.setEnabled(has_pattern)

    def _default_action(self):
        if self._opt_repl.isChecked():
            if self.search_in() in _IN_FILES:
                self.replace_all()
            else:
                self.replace()
        elif self.search_in() in _IN_FILES:
            self.find_all()
        else:
            self.find_next()

    def _browse_dirs(self):
        path = QFileDialog.getExistingDirectory(self, "Select Directory", self._dirs.text())
        if path:
            self._dirs.setText(path)

    # --- option translation

    def _case_sensitive(self):
        if self._opt_case.value == CASE_SMART:
            pattern = self._pattern.text()
            return pattern != pattern.lower()
        return self._opt_case.value == CASE_MATCH

    def _scintilla_flags(self):
        flags = 0
        if self._case_sensitive():
            flags |= Scintilla.FindOption.MatchCase
        if self._opt_word.isChecked():
            flags |= Scintilla.FindOption.WholeWord
        if self._opt_regex.isChecked():
            # RegExp alone means Scintilla's own limited legacy dialect,
            # where bare "(" ")" are literal characters, not groups (you'd
            # need "\(" "\)" instead). Cxx11RegEx switches to C++11
            # std::regex with ECMAScript syntax -- the familiar kind every
            # other modern editor uses -- and still needs RegExp set too.
            flags |= Scintilla.FindOption.RegExp | Scintilla.FindOption.Cxx11RegEx
        return flags

    def _search_kwargs(self):
        return dict(
            case_sensitive=self._case_sensitive(),
            whole_word=self._opt_word.isChecked(),
            use_regex=self._opt_regex.isChecked(),
        )

    def _range(self, editor):
        if self.search_in() == SEARCH_SELECTION and self._selection_range:
            return self._selection_range
        return 0, editor.length()

    # --- current document / selection

    def find_next(self):
        self._find(backward=False)

    def find_previous(self):
        self._find(backward=True)

    def _find(self, backward):
        if self.search_in() == SEARCH_OPEN_FILES:
            self.find_all()
            return
        editor = self._editor
        text = self._pattern.text()
        if editor is None or not text:
            return
        lo, hi = self._range(editor)
        flags = self._scintilla_flags()
        if backward:
            here = max(lo, editor.selectionStart())
            start, end = editor.findText(flags, text, here, lo)
            if start == -1:
                start, end = editor.findText(flags, text, hi, here)
        else:
            here = min(hi, max(lo, editor.currentPos()))
            start, end = editor.findText(flags, text, here, hi)
            if start == -1:
                start, end = editor.findText(flags, text, lo, here)
        if start == -1:
            self.message.emit(f'"{text}" was not found')
            return
        editor.setSel(start, end)
        editor.scrollRange(start, end)

    def replace(self):
        editor = self._editor
        if editor is None or not self._pattern.text():
            return
        sel_start, sel_end = editor.selectionStart(), editor.selectionEnd()
        if sel_start == sel_end:
            # Nothing selected yet: find first, don't replace blind.
            self.find_next()
            return
        new_len = self._replace_target(editor, sel_start, sel_end)
        editor.setSel(sel_start, sel_start + new_len)
        self.find_next()

    def _replace_target(self, editor, start, end):
        replacement = self._repl.text()
        editor.setSearchFlags(self._scintilla_flags())
        editor.setTargetRange(start, end)
        byte_len = len(replacement.encode("utf-8"))
        if self._opt_regex.isChecked():
            return editor.replaceTargetRE(byte_len, replacement)
        return editor.replaceTarget(byte_len, replacement)

    def replace_all(self):
        if self.search_in() in _IN_FILES or self.search_in() == SEARCH_OPEN_FILES:
            self._replace_all_in_files()
            return
        editor = self._editor
        pattern = self._pattern.text()
        if editor is None or not pattern:
            return
        pos, hi = self._range(editor)
        pattern_len = len(pattern.encode("utf-8"))
        count = 0
        # One undo step for the whole Replace All, like Komodo.
        editor.beginUndoAction()
        try:
            while pos <= hi:
                editor.setSearchFlags(self._scintilla_flags())
                editor.setTargetRange(pos, hi)
                found = editor.searchInTarget(pattern_len, pattern)
                if found == -1:
                    break
                old_len = editor.targetEnd() - editor.targetStart()
                new_len = self._replace_target(editor, editor.targetStart(), editor.targetEnd())
                count += 1
                hi += new_len - old_len
                # An empty regex match must still advance.
                pos = found + new_len + (1 if old_len == 0 else 0)
        finally:
            editor.endUndoAction()
        if self._selection_range:
            self._selection_range = (self._selection_range[0], hi)
        self.message.emit(f"{count} replacement(s) made" if count else f'"{pattern}" was not found')

    def mark_all(self):
        """Komodo bookmarks every matching line; qtedit has no bookmarks
        yet, so matches get a highlight indicator instead."""
        editor = self._editor
        pattern = self._pattern.text()
        if editor is None or not pattern:
            return
        lo, hi = self._range(editor)
        editor.indicSetStyle(MARK_ALL_INDICATOR, Scintilla.IndicatorStyle.RoundBox)
        editor.indicSetFore(MARK_ALL_INDICATOR, 0xFF8A3F)
        editor.setIndicatorCurrent(MARK_ALL_INDICATOR)
        editor.indicatorClearRange(0, editor.length())
        flags = self._scintilla_flags()
        count = 0
        pos = lo
        while pos < hi:
            start, end = editor.findText(flags, pattern, pos, hi)
            if start == -1:
                break
            editor.indicatorFillRange(start, max(end - start, 1))
            count += 1
            pos = max(end, start + 1)
        self.message.emit(f"{count} match(es) marked" if count else f'"{pattern}" was not found')

    # --- Find All (any context) and the in-files modes

    def find_all(self):
        pattern = self._pattern.text()
        if not pattern:
            return
        search_in = self.search_in()
        if search_in in (SEARCH_DOCUMENT, SEARCH_SELECTION):
            editor = self._editor
            if editor is None:
                return
            text = editor.current_text()
            path = editor.filepath or "untitled"
            hits = list(fif.search_text(path, text, pattern, **self._search_kwargs()))
            if search_in == SEARCH_SELECTION and self._selection_range:
                lo = editor.countCharacters(0, self._selection_range[0])
                hi = editor.countCharacters(0, self._selection_range[1])
                hits = [h for h in hits if lo <= h.abs_start and h.abs_end <= hi]
            self._report_hits(hits)
            return
        paths = self._resolve_paths()
        if paths is None:
            return
        self._start_thread(SearchWorker(paths, pattern, self._search_kwargs()), self._report_hits)

    def _report_hits(self, hits):
        self.hits_found.emit(hits)
        self.message.emit(f"{len(hits)} match(es) found")
        # find2.p.js: the frame closes once results are shown, unless
        # pinned (pin_find_frame, off by default).
        self.hide_bar()

    def _resolve_paths(self):
        search_in = self.search_in()
        if search_in == SEARCH_OPEN_FILES:
            return list(self.open_files_provider())
        roots = [d for d in re.split(r"[:;]", self._dirs.text()) if d]
        if not roots:
            self.message.emit("No directories to search")
            return None
        paths = []
        for root in roots:
            paths.extend(
                fif.search_dir(
                    root,
                    recursive=self._subdirs.isChecked(),
                    include_glob=self._includes.text() or "*",
                    exclude_glob=self._excludes.text(),
                )
            )
        return paths

    def _replace_all_in_files(self):
        pattern = self._pattern.text()
        if not pattern:
            return
        paths = self._resolve_paths()
        if paths is None:
            return
        worker = PlanWorker(paths, pattern, self._repl.text(), self._search_kwargs())
        self._start_thread(worker, self._on_plan_finished)

    def _on_plan_finished(self, planned):
        if not planned:
            self.message.emit(f'"{self._pattern.text()}" was not found')
            return
        base_dir = self._dirs.text() if self.search_in() in _IN_FILES else ""
        preview = ReplacePreviewDialog(planned, base_dir, self)
        if preview.exec() != QDialog.DialogCode.Accepted:
            return
        selected = preview.selected_replacements()
        undo_record = fif.apply_selected_replacements(selected)
        if not undo_record:
            QMessageBox.information(self, "Replace All", "Nothing selected -- no changes made.")
            return
        all_hits = [p.hit for r in selected for p in r.planned if p.selected]
        self.hits_found.emit(all_hits)
        self.replacements_applied.emit(undo_record)
        self.message.emit(
            f"Replaced {len(all_hits)} occurrence(s) in {len(undo_record)} file(s)"
        )

    def _start_thread(self, worker, on_finished):
        if self._thread is not None:
            return
        self._thread = QThread(self)
        self._worker = worker
        worker.moveToThread(self._thread)
        self._thread.started.connect(worker.run)
        worker.finished.connect(on_finished)
        worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._on_thread_done)
        self.message.emit("Searching...")
        self._thread.start()

    def _on_thread_done(self):
        self._thread = None
        self._worker = None
