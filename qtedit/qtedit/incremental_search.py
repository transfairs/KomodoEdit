"""Komodo's incremental search bar (find/findbar.xml <ko-findbar> driven by
library/findController.js), bound to Ctrl+F (cmd_startIncrementalSearch in
the Legacy keybinding scheme).

It lives in the editor view right after Scintilla; with the classic
statusbar moved to the end (`-moz-box-ordinal-group: 2`), that puts it
directly above the statusbar. Behavior follows findController.js:

- starting preloads the single-line selection (else the last isearch
  pattern) and highlights all its matches without moving the caret
- typing searches from the position the search started at
- Enter / the arrow buttons search again; Esc closes and returns focus
- Shift+Right at the end of the textbox extends the pattern from the editor
- case sensitivity and pattern type are remembered (isearchCaseSensitivity,
  isearchType), defaulting to smart case and plain text
"""
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QMenu, QToolButton, QWidget
from pyside6_scintilla import Scintilla

from qtedit import icons
from qtedit.prefs import get_global_prefs
from qtedit.skin.css import komodo_stylesheet, load_colors

# koIFindOptions values, as stored in the isearch* prefs.
FOC_INSENSITIVE, FOC_SENSITIVE, FOC_SMART = 0, 1, 2
FOT_SIMPLE, FOT_WILDCARD, FOT_REGEX = 0, 1, 2
_CASE_NAMES = {FOC_INSENSITIVE: "FOC_INSENSITIVE", FOC_SENSITIVE: "FOC_SENSITIVE", FOC_SMART: "FOC_SMART"}
_TYPE_NAMES = {FOT_SIMPLE: "FOT_SIMPLE", FOT_WILDCARD: "FOT_WILDCARD", FOT_REGEX: "FOT_REGEX_PYTHON"}
_CASE_LABELS = [
    (FOC_INSENSITIVE, "Insensitive", "Search case-insensitively"),
    (FOC_SENSITIVE, "Sensitive", "Search case-sensitively"),
    (FOC_SMART, "Smart", "Search case-sensitively only if the search string is mixed case"),
]
_TYPE_LABELS = [
    (FOT_SIMPLE, "Plain", "Search using plain text"),
    (FOT_WILDCARD, "Wildcard", "Search using wild cards"),
    (FOT_REGEX, "RegEx", "Search using regular expressions (Python syntax)"),
]

# Default.ksf Indicators.find_highlighting, on koILintResult's
# DECORATOR_FIND_HIGHLIGHT indicator number.
FIND_HIGHLIGHT_INDICATOR = 27
FIND_HIGHLIGHT_COLOR = 12493441  # BGR, as stored in the .ksf
FIND_HIGHLIGHT_ALPHA = 100

PREF_CASE = "isearchCaseSensitivity"
PREF_TYPE = "isearchType"


def _glyph(selector, color=None):
    content = komodo_stylesheet().value(selector, "content")
    return icons.glyph(icons.css_glyph(content) if content else "?", 16,
                       QColor(color or load_colors()["icons"]))


class IncrementalSearchBar(QWidget):
    closed = Signal()
    open_dialog_requested = Signal(str)  # pattern; findbar's "open find dialog"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ko-findbar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self._editor = None
        self._start_pos = 0
        self._last_pattern = ""
        prefs = get_global_prefs()
        self.case_sensitivity = int(prefs.get(PREF_CASE, FOC_SMART))
        self.pattern_type = int(prefs.get(PREF_TYPE, FOT_SIMPLE))

        self._textbox = QLineEdit()
        self._textbox.setObjectName("ko-findbar-textbox")
        self._textbox.setPlaceholderText("Incremental search ready")
        width = komodo_stylesheet().value("ko-findbar .ko-findbar-textbox", "width", "30em")
        font = self._textbox.font()
        em_px = font.pixelSize() if font.pixelSize() > 0 else round(font.pointSizeF() * 96 / 72)
        self._textbox.setFixedWidth(round(float(width.rstrip("em")) * em_px))
        self._textbox.textEdited.connect(self._on_input)
        self._textbox.installEventFilter(self)

        self._next = self._button("ko-findbar-next", "Find the next occurrence",
                                  _glyph(".ko-findbar-next:before"))
        self._next.clicked.connect(lambda: self.search_again(backwards=False))
        self._prev = self._button("ko-findbar-prev", "Find the previous occurrence",
                                  _glyph(".ko-findbar-prev:before"))
        self._prev.clicked.connect(lambda: self.search_again(backwards=True))

        self._case_button = self._button("ko-findbar-case-sensitive", "", None)
        self._case_button.setMenu(self._radio_menu(_CASE_LABELS, self.case_sensitivity, self._set_case))
        self._case_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._type_button = self._button("ko-findbar-pattern-type", "", None)
        self._type_button.setMenu(self._radio_menu(_TYPE_LABELS, self.pattern_type, self._set_type))
        self._type_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._open_dialog = self._button("ko-findbar-open-dialog", "Open the find dialog",
                                         _glyph(".ko-findbar-open-dialog:before"))
        self._open_dialog.clicked.connect(
            lambda: self.open_dialog_requested.emit(self._textbox.text())
        )
        self._status = QLabel()
        self._status.setObjectName("ko-findbar-status-text")
        close = self._button("ko-findbar-closebutton", "Close find bar",
                             _glyph(".tab-close-button:before"))
        close.clicked.connect(self.close_bar)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(0)
        for widget in (self._textbox, self._next, self._prev, self._case_button,
                       self._type_button, self._open_dialog):
            layout.addWidget(widget)
        layout.addSpacing(8)
        layout.addWidget(self._status)
        layout.addStretch(1)
        layout.addWidget(close)
        self._update_option_icons()
        self.hide()

    def _button(self, name, tooltip, icon):
        button = QToolButton()
        button.setObjectName(name)
        button.setToolTip(tooltip)
        if icon is not None:
            button.setIcon(icon)
        return button

    def _radio_menu(self, entries, current, on_select):
        menu = QMenu(self)
        group = QActionGroup(menu)
        for value, label, tooltip in entries:
            action = QAction(label, menu, checkable=True)
            action.setToolTip(tooltip)
            action.setChecked(value == current)
            action.triggered.connect(lambda _c=False, v=value: on_select(v))
            group.addAction(action)
            menu.addAction(action)
        return menu

    def _set_case(self, value):
        self.case_sensitivity = value
        self._update_option_icons()
        self._on_input(self._textbox.text())

    def _set_type(self, value):
        self.pattern_type = value
        self._update_option_icons()
        self._on_input(self._textbox.text())

    def _update_option_icons(self):
        case = _CASE_NAMES[self.case_sensitivity]
        self._case_button.setIcon(_glyph(
            f'.ko-findbar-case-sensitive[value="{case}"] > .toolbarbutton-text:before'))
        self._case_button.setToolTip(_CASE_LABELS[self.case_sensitivity][2])
        kind = _TYPE_NAMES[self.pattern_type]
        self._type_button.setIcon(_glyph(
            f'.ko-findbar-pattern-type[value="{kind}"] > .toolbarbutton-text:before'))
        self._type_button.setToolTip(_TYPE_LABELS[self.pattern_type][2])

    # --- findController.js: start / stop

    def start(self, editor):
        """do_cmd_startIncrementalSearch."""
        if editor is None:
            return
        self._editor = editor
        self._start_pos = min(editor.currentPos(), editor.anchor())
        start, end = editor.selectionStart(), editor.selectionEnd()
        pattern = bytes(editor.textRange(start, end)).decode("utf-8", errors="replace")
        if "\n" in pattern:
            pattern = ""  # ignore multi-line selections
        pattern = pattern or self._last_pattern
        self._last_pattern = pattern
        self._set_status(None)
        self._clear_highlight()
        self.show()
        self._textbox.setText(pattern)
        self._textbox.setFocus()
        if pattern:
            self._textbox.selectAll()
            # Highlight the other occurrences without moving the caret.
            self._highlight_all(pattern)

    def close_bar(self):
        """_stopIncrementalSearch: remember the options, hand focus back."""
        prefs = get_global_prefs()
        prefs.set(PREF_CASE, self.case_sensitivity)
        prefs.set(PREF_TYPE, self.pattern_type)
        self.hide()
        self.closed.emit()

    def set_editor(self, editor):
        if editor is not self._editor and self.isVisible():
            self.close_bar()
        self._editor = editor

    # --- searching

    def _flags(self, pattern):
        flags = 0
        sensitive = self.case_sensitivity == FOC_SENSITIVE or (
            self.case_sensitivity == FOC_SMART and pattern != pattern.lower()
        )
        if sensitive:
            flags |= Scintilla.FindOption.MatchCase
        if self.pattern_type != FOT_SIMPLE:
            flags |= Scintilla.FindOption.RegExp | Scintilla.FindOption.Cxx11RegEx
        return flags

    def _scintilla_pattern(self, pattern):
        if self.pattern_type == FOT_WILDCARD:
            return ".*".join(".".join(re.escape(p) for p in part.split("?"))
                             for part in pattern.split("*"))
        return pattern

    def _find(self, pattern, start, end):
        return self._editor.findText(self._flags(pattern), self._scintilla_pattern(pattern), start, end)

    def _on_input(self, text):
        """FindController.search(): retype searches from the start position."""
        editor = self._editor
        if editor is None:
            return
        self._last_pattern = text
        self._clear_highlight()
        if not text:
            self._set_status(None)
            editor.setSel(self._start_pos, self._start_pos)
            return
        found = self._find(text, self._start_pos, editor.length())
        wrapped = False
        if found[0] == -1:
            found = self._find(text, 0, self._start_pos)
            wrapped = found[0] != -1
        self._show_result(text, found, "Reached end of document, continued from top" if wrapped else None)

    def search_again(self, backwards=False):
        editor = self._editor
        text = self._textbox.text()
        if editor is None or not text:
            return
        if backwards:
            here = min(editor.currentPos(), editor.anchor())
            found = self._find(text, here, 0)
            wrapped = None
            if found[0] == -1:
                found = self._find(text, editor.length(), here)
                wrapped = "Reached start of document, continued from bottom"
        else:
            here = max(editor.currentPos(), editor.anchor())
            found = self._find(text, here, editor.length())
            wrapped = None
            if found[0] == -1:
                found = self._find(text, 0, here)
                wrapped = "Reached end of document, continued from top"
        self._show_result(text, found, wrapped if found[0] != -1 else None)

    def _show_result(self, text, found, wrapped_message):
        editor = self._editor
        start, end = found
        if start == -1:
            # find2.properties findNotFound, pluralized like Komodo.
            self._set_status("not-found", "0 occurrences were found.")
            return
        editor.setSel(start, end)
        editor.scrollRange(start, end)
        self._set_status("wrapped" if wrapped_message else None, wrapped_message)
        self._highlight_all(text)

    def _set_status(self, kind, text=None):
        """findbar.setStatus(): the not-found state tints the textbox."""
        self._status.setText(text or "")
        self._textbox.setProperty("notFound", kind == "not-found")
        self._textbox.style().unpolish(self._textbox)
        self._textbox.style().polish(self._textbox)

    def _highlight_all(self, pattern):
        editor = self._editor
        editor.indicSetStyle(FIND_HIGHLIGHT_INDICATOR, Scintilla.IndicatorStyle.StraightBox)
        editor.indicSetFore(FIND_HIGHLIGHT_INDICATOR, FIND_HIGHLIGHT_COLOR)
        editor.indicSetAlpha(FIND_HIGHLIGHT_INDICATOR, FIND_HIGHLIGHT_ALPHA)
        editor.indicSetOutlineAlpha(FIND_HIGHLIGHT_INDICATOR, FIND_HIGHLIGHT_ALPHA)
        editor.indicSetUnder(FIND_HIGHLIGHT_INDICATOR, True)
        editor.setIndicatorCurrent(FIND_HIGHLIGHT_INDICATOR)
        editor.indicatorClearRange(0, editor.length())
        pos, end = 0, editor.length()
        while pos < end:
            start, stop = self._find(pattern, pos, end)
            if start == -1:
                break
            editor.indicatorFillRange(start, max(stop - start, 1))
            pos = max(stop, start + 1)

    def _clear_highlight(self):
        if self._editor is not None:
            self._editor.setIndicatorCurrent(FIND_HIGHLIGHT_INDICATOR)
            self._editor.indicatorClearRange(0, self._editor.length())

    # --- keys (findbar.xml <handlers>)

    def eventFilter(self, obj, event):
        if obj is self._textbox and event.type() == event.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.close_bar()
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.search_again()
                return True
            if (key == Qt.Key.Key_Right
                    and event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                    and self._textbox.cursorPosition() == len(self._textbox.text())
                    and self._editor is not None):
                editor = self._editor
                pos = max(editor.currentPos(), editor.anchor())
                if pos < editor.length():
                    next_char = bytes(editor.textRange(pos, editor.positionAfter(pos))).decode(
                        "utf-8", errors="replace")
                    self._textbox.setText(self._textbox.text() + next_char)
                    self._on_input(self._textbox.text())
                return True
        return super().eventFilter(obj, event)
