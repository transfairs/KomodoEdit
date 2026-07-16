"""Git status/stage/commit panel -- UI/wiring only, all git operations live
in vcs.py. No filesystem watcher: refreshes on open and on explicit user
action (Refresh button, after stage/unstage/commit), matching the "manual
refresh is enough for v1" call in the plan doc.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qtedit import vcs

PATH_ROLE = Qt.ItemDataRole.UserRole + 1
STAGED_ROLE = Qt.ItemDataRole.UserRole + 2


class VCSPanel(QWidget):
    diff_requested = Signal(str, bool)  # path, staged

    def __init__(self, base_dir, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Status", "File"])
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        self._tree.itemDoubleClicked.connect(self._on_double_clicked)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        button_row = QHBoxLayout()
        button_row.addWidget(refresh_btn)
        button_row.addStretch(1)

        self._commit_message = QPlainTextEdit()
        self._commit_message.setPlaceholderText("Commit message")
        self._commit_message.setMaximumHeight(60)
        commit_btn = QPushButton("Commit")
        commit_btn.clicked.connect(self._commit)
        commit_row = QHBoxLayout()
        commit_row.addWidget(self._commit_message)
        commit_row.addWidget(commit_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(button_row)
        layout.addWidget(self._tree)
        layout.addLayout(commit_row)

        self.refresh()

    def refresh(self):
        self._tree.clear()
        for status in vcs.git_status(self.base_dir):
            code = f"{status.index_code}{status.worktree_code}"
            item = QTreeWidgetItem([code, status.path])
            item.setData(0, PATH_ROLE, status.path)
            item.setData(0, STAGED_ROLE, status.is_staged)
            self._tree.addTopLevelItem(item)
        for column in range(2):
            self._tree.resizeColumnToContents(column)

    def _selected_paths(self):
        return [item.data(0, PATH_ROLE) for item in self._tree.selectedItems()]

    def _on_double_clicked(self, item, _column):
        path = item.data(0, PATH_ROLE)
        staged = item.data(0, STAGED_ROLE)
        self.diff_requested.emit(path, bool(staged))

    def _show_context_menu(self, pos):
        item = self._tree.itemAt(pos)
        if item is None:
            return
        staged = item.data(0, STAGED_ROLE)
        menu = QMenu(self)
        if staged:
            menu.addAction("Unstage").triggered.connect(self._unstage_selected)
        else:
            menu.addAction("Stage").triggered.connect(self._stage_selected)
        menu.addAction("Show Diff").triggered.connect(
            lambda: self.diff_requested.emit(item.data(0, PATH_ROLE), bool(staged))
        )
        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _stage_selected(self):
        paths = self._selected_paths()
        if paths:
            vcs.git_stage(self.base_dir, paths)
            self.refresh()

    def _unstage_selected(self):
        paths = self._selected_paths()
        if paths:
            vcs.git_unstage(self.base_dir, paths)
            self.refresh()

    def _commit(self):
        message = self._commit_message.toPlainText().strip()
        if not message:
            QMessageBox.warning(self, "Commit", "Enter a commit message first.")
            return
        ok, output = vcs.git_commit(self.base_dir, message)
        if not ok:
            QMessageBox.warning(self, "Commit", f"Commit failed:\n{output}")
            return
        self._commit_message.clear()
        self.refresh()
