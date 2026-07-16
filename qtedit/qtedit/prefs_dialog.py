from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
)

from qtedit.prefs import get_global_prefs


class PreferencesDialog(QDialog):
    """Edits the global PrefSet directly and live -- each widget writes
    through on change rather than batching into an OK/Cancel-gated commit,
    so open editors update immediately (see editor.py's `changed` hookup)
    and there's nothing to lose by closing the dialog early."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self._prefs = get_global_prefs()

        self._use_tabs = QCheckBox()
        self._use_tabs.setChecked(self._prefs.get("useTabs"))
        self._use_tabs.toggled.connect(
            lambda checked: self._prefs.set("useTabs", checked)
        )

        self._tab_width = QSpinBox()
        self._tab_width.setRange(1, 16)
        self._tab_width.setValue(self._prefs.get("tabWidth"))
        self._tab_width.valueChanged.connect(
            lambda value: self._prefs.set("tabWidth", value)
        )

        self._indent_width = QSpinBox()
        self._indent_width.setRange(1, 16)
        self._indent_width.setValue(self._prefs.get("indentWidth"))
        self._indent_width.valueChanged.connect(
            lambda value: self._prefs.set("indentWidth", value)
        )

        form = QFormLayout()
        form.addRow("Use tabs", self._use_tabs)
        form.addRow("Tab width", self._tab_width)
        form.addRow("Indent width", self._indent_width)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        buttons.accepted.connect(self.close)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)
