"""Komodo's "save modified files" prompt (viewManager.offerToSave in
views.p.js via dialogs/selectFromList.xul): a list of the dirty buffers,
all selected, with Save / Do Not Save / Cancel.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QListWidget,
    QVBoxLayout,
)

# offerToSave assigns the prompt string to `title` (a Komodo bug), so the
# window shows it as its title and no prompt line appears.
TITLE = "Please select the files you wish to save"


class SaveModifiedDialog(QDialog):
    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.resize(400, 350)  # selectFromList.xul width/height
        self.setMinimumWidth(400)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        # crop="center": no horizontal scrolling, elide in the middle.
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.list.addItems(labels)
        self.list.selectAll()

        buttons = QDialogButtonBox()
        self._save = buttons.addButton("Save", QDialogButtonBox.ButtonRole.AcceptRole)
        self._dont = buttons.addButton("Do Not Save", QDialogButtonBox.ButtonRole.DestructiveRole)
        buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        self._save.setDefault(True)
        self._choice = None
        buttons.clicked.connect(self._clicked)

        layout = QVBoxLayout(self)
        layout.addWidget(self.list)
        layout.addWidget(buttons)

    def _clicked(self, button):
        self._choice = button
        self.accept() if button in (self._save, self._dont) else self.reject()

    def ask(self):
        """Indexes to save ([] for Do Not Save), or None for Cancel."""
        if self.exec() != QDialog.DialogCode.Accepted:
            return None
        if self._choice is self._dont:
            return []
        return sorted(self.list.row(item) for item in self.list.selectedItems())
