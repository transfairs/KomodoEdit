"""Dialog for creating or editing a toolbox item's actual content.

The New Snippet/Command context-menu actions originally only asked for a
name, with no way to set what the snippet inserts or the command runs --
this is the fix, reused for both creating a new item and editing an
existing one's content (renaming isn't supported here; delete+recreate if
a name needs to change)."""
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
)

from qtedit.toolbox.model import COMMAND, SNIPPET


class ToolboxItemDialog(QDialog):
    def __init__(
        self, item_type, name="", value="", cwd="", editing_name=True, parent=None
    ):
        super().__init__(parent)
        verb = "New" if editing_name else "Edit"
        self.setWindowTitle(f"{verb} {item_type.title()}")
        self._item_type = item_type

        form = QFormLayout()

        self._name_edit = QLineEdit(name)
        self._name_edit.setEnabled(editing_name)
        form.addRow("Name", self._name_edit)

        if item_type == SNIPPET:
            self._value_edit = QPlainTextEdit(value)
            self._value_edit.setPlaceholderText("Text to insert...")
            form.addRow("Snippet text", self._value_edit)
            self._cwd_edit = None
        else:
            self._value_edit = QLineEdit(value)
            self._value_edit.setPlaceholderText("Shell command to run...")
            form.addRow("Command", self._value_edit)
            self._cwd_edit = QLineEdit(cwd)
            self._cwd_edit.setPlaceholderText("(optional) working directory")
            form.addRow("Working directory", self._cwd_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def name(self):
        return self._name_edit.text().strip()

    def value(self):
        if self._item_type == SNIPPET:
            return self._value_edit.toPlainText()
        return self._value_edit.text()

    def cwd(self):
        return self._cwd_edit.text().strip() if self._cwd_edit is not None else ""
