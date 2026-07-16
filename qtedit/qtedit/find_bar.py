"""Inline find/replace bar.

All the actual searching/replacing is Scintilla's own engine
(`findText`/`searchInTarget`/`replaceTarget`/`replaceTargetRE`, already
exposed 1:1 by pyside6-scintilla) -- this widget is UI and wiring only, no
search logic of its own. It's stateless across tabs: `set_editor()` points
it at whichever CodeEditor is currently active, and every action operates
on that editor directly rather than the bar keeping its own cursor/match
state.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from pyside6_scintilla import Scintilla


class FindBar(QWidget):
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._editor = None

        self._find_edit = QLineEdit()
        self._find_edit.setPlaceholderText("Find")
        self._find_edit.returnPressed.connect(self.find_next)

        self._replace_edit = QLineEdit()
        self._replace_edit.setPlaceholderText("Replace")
        self._replace_edit.returnPressed.connect(self.replace_current)

        self._match_case = QCheckBox("Match case")
        self._whole_word = QCheckBox("Whole word")
        self._regex = QCheckBox("Regex")

        find_next_btn = QPushButton("Find Next")
        find_next_btn.clicked.connect(self.find_next)
        find_prev_btn = QPushButton("Find Previous")
        find_prev_btn.clicked.connect(self.find_previous)
        replace_btn = QPushButton("Replace")
        replace_btn.clicked.connect(self.replace_current)
        replace_all_btn = QPushButton("Replace All")
        replace_all_btn.clicked.connect(self.replace_all)

        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setToolTip("Close (Esc)")
        close_btn.clicked.connect(self.hide_bar)

        self._status_label = QLabel()

        find_row = QHBoxLayout()
        find_row.addWidget(self._find_edit)
        find_row.addWidget(find_next_btn)
        find_row.addWidget(find_prev_btn)
        find_row.addWidget(self._match_case)
        find_row.addWidget(self._whole_word)
        find_row.addWidget(self._regex)
        find_row.addWidget(self._status_label, 1)
        find_row.addWidget(close_btn)

        replace_row = QHBoxLayout()
        replace_row.addWidget(self._replace_edit)
        replace_row.addWidget(replace_btn)
        replace_row.addWidget(replace_all_btn)
        replace_row.addStretch(1)

        layout = QVBoxLayout()
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addLayout(find_row)
        layout.addLayout(replace_row)
        self.setLayout(layout)

    def set_editor(self, editor):
        self._editor = editor

    def show_bar(self):
        self.show()
        self._status_label.setText("")
        self._find_edit.setFocus()
        self._find_edit.selectAll()

    def hide_bar(self):
        self.hide()
        self.closed.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide_bar()
            return
        super().keyPressEvent(event)

    def _flags(self):
        flags = 0
        if self._match_case.isChecked():
            flags |= Scintilla.FindOption.MatchCase
        if self._whole_word.isChecked():
            flags |= Scintilla.FindOption.WholeWord
        if self._regex.isChecked():
            # RegExp alone means Scintilla's own limited legacy dialect,
            # where bare "(" ")" are literal characters, not groups (you'd
            # need "\(" "\)" instead). Cxx11RegEx switches to C++11
            # std::regex with ECMAScript syntax -- the familiar kind every
            # other modern editor uses -- and still needs RegExp set too.
            flags |= Scintilla.FindOption.RegExp | Scintilla.FindOption.Cxx11RegEx
        return flags

    def find_next(self):
        editor = self._editor
        text = self._find_edit.text()
        if editor is None or not text:
            return
        pos = editor.currentPos()
        length = editor.length()
        start, end = editor.findText(self._flags(), text, pos, length)
        if start == -1:
            start, end = editor.findText(self._flags(), text, 0, pos)
        self._apply_match(editor, start, end)

    def find_previous(self):
        editor = self._editor
        text = self._find_edit.text()
        if editor is None or not text:
            return
        search_from = editor.selectionStart()
        start, end = editor.findText(self._flags(), text, search_from, 0)
        if start == -1:
            start, end = editor.findText(self._flags(), text, editor.length(), search_from)
        self._apply_match(editor, start, end)

    def _apply_match(self, editor, start, end):
        if start == -1:
            self._status_label.setText("Not found")
            return
        self._status_label.setText("")
        editor.setSel(start, end)
        editor.scrollRange(start, end)

    def replace_current(self):
        editor = self._editor
        find_text = self._find_edit.text()
        if editor is None or not find_text:
            return
        sel_start = editor.selectionStart()
        sel_end = editor.selectionEnd()
        if sel_start == sel_end:
            # Nothing selected yet -- find first, don't replace blind.
            self.find_next()
            return
        replace_text = self._replace_edit.text()
        editor.setSearchFlags(self._flags())
        editor.setTargetRange(sel_start, sel_end)
        if self._regex.isChecked():
            new_len = editor.replaceTargetRE(len(replace_text.encode("utf-8")), replace_text)
        else:
            new_len = editor.replaceTarget(len(replace_text.encode("utf-8")), replace_text)
        editor.setSel(sel_start, sel_start + new_len)
        self.find_next()

    def replace_all(self):
        editor = self._editor
        find_text = self._find_edit.text()
        if editor is None or not find_text:
            return
        replace_text = self._replace_edit.text()
        flags = self._flags()
        editor.setSearchFlags(flags)
        editor.setTargetRange(0, editor.length())
        find_byte_len = len(find_text.encode("utf-8"))
        replace_byte_len = len(replace_text.encode("utf-8"))
        count = 0
        while True:
            pos = editor.searchInTarget(find_byte_len, find_text)
            if pos == -1:
                break
            if self._regex.isChecked():
                new_len = editor.replaceTargetRE(replace_byte_len, replace_text)
            else:
                new_len = editor.replaceTarget(replace_byte_len, replace_text)
            count += 1
            editor.setTargetRange(pos + new_len, editor.length())
        self._status_label.setText(f"{count} replaced" if count else "Not found")
