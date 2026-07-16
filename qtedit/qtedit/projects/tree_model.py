"""QStandardItemModel view over projects/model.py's pure tree."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QApplication, QStyle

# Every row gets NODE_ROLE: the ProjectFile/ProjectFolder dataclass instance
# it represents (used for double-click-to-open and context-menu removal).
NODE_ROLE = Qt.ItemDataRole.UserRole + 1
IS_FILE_ROLE = Qt.ItemDataRole.UserRole + 2

# Loosely follows the surviving scc_* status vocabulary from Komodo's old
# (never-implemented, see vcs.py's docstring) SCC skin -- not an exact
# reproduction, just the same rough ok/add/delete/edit/conflict semantics.
_CONFLICT_COLOR = QColor(0xE0, 0x5A, 0x5A)
_DELETED_COLOR = QColor(0xE0, 0x5A, 0x5A)
_ADDED_COLOR = QColor(0x6A, 0xC2, 0x6A)
_MODIFIED_COLOR = QColor(0xE0, 0xA6, 0x3E)
_UNTRACKED_COLOR = QColor(0x96, 0x96, 0x96)


def _status_color(code):
    index_code, worktree_code = code[0], code[1]
    if index_code == "?" and worktree_code == "?":
        return _UNTRACKED_COLOR
    if index_code == "U" or worktree_code == "U":
        return _CONFLICT_COLOR
    if index_code == "D" or worktree_code == "D":
        return _DELETED_COLOR
    if index_code == "A":
        return _ADDED_COLOR
    if index_code == "M" or worktree_code == "M":
        return _MODIFIED_COLOR
    return None


def build_project_model(project, git_status=None):
    """`git_status`, if given: dict mapping a file's project-relative `url`
    to its combined `git status --porcelain` code (e.g. "M ", "??", "A ")
    -- colors matching file rows, purely informational (see vcs.py)."""
    model = QStandardItemModel()
    model.setHorizontalHeaderLabels([project.name])
    _populate(model.invisibleRootItem(), project.folders, project.files, git_status or {})
    return model


def _populate(parent_item, folders, files, git_status):
    style = QApplication.instance().style()
    dir_icon = style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)
    file_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)

    for folder in folders:
        folder_item = QStandardItem(dir_icon, folder.name)
        folder_item.setEditable(False)
        folder_item.setData(folder, NODE_ROLE)
        folder_item.setData(False, IS_FILE_ROLE)
        parent_item.appendRow(folder_item)
        _populate(folder_item, folder.folders, folder.files, git_status)

    for file in files:
        file_item = QStandardItem(file_icon, file.name)
        file_item.setEditable(False)
        file_item.setToolTip(file.url)
        file_item.setData(file, NODE_ROLE)
        file_item.setData(True, IS_FILE_ROLE)
        code = git_status.get(file.url)
        if code:
            color = _status_color(code)
            if color is not None:
                file_item.setForeground(QBrush(color))
        parent_item.appendRow(file_item)
