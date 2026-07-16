"""QStandardItemModel view over toolbox/model.py's pure tree."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QApplication, QStyle

from qtedit.toolbox.model import scan_toolbox

# Every row gets FOLDER_PATH_ROLE: the directory a "New Snippet/Command/
# Folder" action on that row should create into (a folder row's own path,
# or an item row's containing directory). Only item rows also get
# TOOLBOX_ITEM_ROLE (the parsed ToolboxItem); folder rows leave it unset.
FOLDER_PATH_ROLE = Qt.ItemDataRole.UserRole + 1
TOOLBOX_ITEM_ROLE = Qt.ItemDataRole.UserRole + 2


def build_toolbox_model(root_path, project_toolbox_root=None):
    """Scan `root_path` and return a populated QStandardItemModel. The
    root folder itself isn't shown as a row -- the tree view's own root
    already represents it.

    If `project_toolbox_root` is given (a project's .komodotools
    directory), its contents are shown as an additional top-level "Project
    Tools" folder ahead of the global items -- matching legacy Komodo's
    additive-section behavior (koIToolbox2HTreeView.addProject) rather than
    replacing the global toolbox. Reuses the same FOLDER_PATH_ROLE/
    TOOLBOX_ITEM_ROLE data the global tree already uses, so the existing
    generic context-menu code in main_window.py needs no changes to work
    for items under this section too.
    """
    model = QStandardItemModel()
    model.setHorizontalHeaderLabels(["Toolbox"])
    root_item = model.invisibleRootItem()

    if project_toolbox_root is not None:
        style = QApplication.instance().style()
        dir_icon = style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        project_folder = scan_toolbox(project_toolbox_root)
        project_item = QStandardItem(dir_icon, "Project Tools")
        project_item.setEditable(False)
        project_item.setData(project_toolbox_root, FOLDER_PATH_ROLE)
        root_item.appendRow(project_item)
        _populate(project_item, project_folder)

    folder = scan_toolbox(root_path)
    _populate(root_item, folder)
    return model


def _populate(parent_item, folder):
    style = QApplication.instance().style()
    dir_icon = style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)
    file_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)

    for sub in folder.folders:
        folder_item = QStandardItem(dir_icon, sub.name)
        folder_item.setEditable(False)
        folder_item.setData(sub.path, FOLDER_PATH_ROLE)
        parent_item.appendRow(folder_item)
        _populate(folder_item, sub)

    for item in folder.items:
        item_row = QStandardItem(file_icon, item.name)
        item_row.setEditable(False)
        item_row.setToolTip(item.type)
        item_row.setData(folder.path, FOLDER_PATH_ROLE)
        item_row.setData(item, TOOLBOX_ITEM_ROLE)
        parent_item.appendRow(item_row)
