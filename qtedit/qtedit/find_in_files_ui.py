"""Background workers and the Replace All preview for the find frame's
"in files" modes (find_bar.py) -- UI/wiring only, all search/replace logic
lives in find_in_files.py. The actual filesystem walk/regex work runs on a
background QThread (search_files()/plan_replacements() are both plain
generators/functions with no Qt dependency, so they're safe to call from
a worker thread as long as results only get handed back to the UI thread
via signals, which is what happens here).
"""
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from qtedit import find_in_files as fif


class SearchWorker(QObject):
    finished = Signal(list)  # list[FileHit]

    def __init__(self, paths, pattern, kwargs):
        super().__init__()
        self._paths = paths
        self._pattern = pattern
        self._kwargs = kwargs
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        hits = list(
            fif.search_files(
                self._paths,
                self._pattern,
                is_cancelled=lambda: self._cancelled,
                **self._kwargs,
            )
        )
        self.finished.emit(hits)


class PlanWorker(QObject):
    finished = Signal(list)  # list[FileReplacement]

    def __init__(self, paths, pattern, replacement, kwargs):
        super().__init__()
        self._paths = paths
        self._pattern = pattern
        self._replacement = replacement
        self._kwargs = kwargs
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        planned = fif.plan_replacements(
            self._paths,
            self._pattern,
            self._replacement,
            is_cancelled=lambda: self._cancelled,
            **self._kwargs,
        )
        self.finished.emit(planned)


class ReplacePreviewDialog(QDialog):
    """Per-hit checklist shown before Replace All actually writes anything
    -- replaces the old single "Replace N occurrences?" summary confirm."""

    def __init__(self, replacements, base_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Replace All -- Preview")
        self.resize(700, 400)
        self._replacements = replacements
        self._base_dir = base_dir

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["", "File", "Line", "Text", "Replacement"])
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._items_by_planned = {}
        for repl in replacements:
            for planned in repl.planned:
                hit = planned.hit
                item = QTreeWidgetItem(
                    [
                        "",
                        _rel(hit.path, base_dir),
                        str(hit.line_no),
                        hit.line_text.strip(),
                        planned.replacement_text,
                    ]
                )
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    0, Qt.CheckState.Checked if planned.selected else Qt.CheckState.Unchecked
                )
                self._tree.addTopLevelItem(item)
                self._items_by_planned[id(planned)] = (item, planned)
        for column in range(5):
            self._tree.resizeColumnToContents(column)

        select_row = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(lambda: self._set_all(Qt.CheckState.Checked))
        select_none_btn = QPushButton("Select None")
        select_none_btn.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        select_row.addWidget(select_all_btn)
        select_row.addWidget(select_none_btn)
        select_row.addStretch(1)

        total = sum(len(r.planned) for r in replacements)
        self._summary = QLabel(f"{total} occurrence(s) in {len(replacements)} file(s)")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self._summary)
        layout.addLayout(select_row)
        layout.addWidget(self._tree)
        layout.addWidget(buttons)

    def _set_all(self, state):
        for i in range(self._tree.topLevelItemCount()):
            self._tree.topLevelItem(i).setCheckState(0, state)

    def _on_accept(self):
        for item, planned in self._items_by_planned.values():
            planned.selected = item.checkState(0) == Qt.CheckState.Checked
        self.accept()

    def selected_replacements(self):
        """The original `replacements` list, with each PlannedReplacement's
        `.selected` updated from the checklist -- pass straight to
        find_in_files.apply_selected_replacements()."""
        return self._replacements


def _rel(path, base_dir):
    import os

    try:
        return os.path.relpath(path, base_dir)
    except ValueError:
        return path
