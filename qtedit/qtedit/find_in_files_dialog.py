"""Find in Files dialog -- UI/wiring only, all search/replace logic lives
in find_in_files.py. Runs the search synchronously on the UI thread (no
QProcess/threading): fine for an MVP on typical project sizes, a known
scaling limit rather than an oversight.
"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from qtedit import find_in_files as fif


class FindInFilesDialog(QDialog):
    # Emits the list[FileHit] from a completed "Find All" so the caller
    # (MainWindow) can populate the Find Results dock.
    hits_found = Signal(list)

    def __init__(self, default_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Find in Files")

        self._find_edit = QLineEdit()
        self._replace_edit = QLineEdit()

        self._dir_edit = QLineEdit(default_dir)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_dir)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self._dir_edit)
        dir_row.addWidget(browse_btn)

        self._include_edit = QLineEdit("*")
        self._exclude_edit = QLineEdit()

        self._recursive = QCheckBox("Search in subdirectories")
        self._recursive.setChecked(True)
        self._match_case = QCheckBox("Match case")
        self._whole_word = QCheckBox("Whole word")
        self._regex = QCheckBox("Regex")

        form = QFormLayout()
        form.addRow("Find:", self._find_edit)
        form.addRow("Replace:", self._replace_edit)
        form.addRow("Directory:", dir_row)
        form.addRow("Include:", self._include_edit)
        form.addRow("Exclude:", self._exclude_edit)
        form.addRow(self._recursive)

        options_row = QHBoxLayout()
        options_row.addWidget(self._match_case)
        options_row.addWidget(self._whole_word)
        options_row.addWidget(self._regex)
        options_row.addStretch(1)

        buttons = QDialogButtonBox()
        find_all_btn = buttons.addButton("Find All", QDialogButtonBox.ButtonRole.ActionRole)
        find_all_btn.clicked.connect(self._on_find_all)
        replace_all_btn = buttons.addButton(
            "Replace All", QDialogButtonBox.ButtonRole.ActionRole
        )
        replace_all_btn.clicked.connect(self._on_replace_all)
        close_btn = buttons.addButton(QDialogButtonBox.StandardButton.Close)
        close_btn.clicked.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(options_row)
        layout.addWidget(buttons)

        self._find_edit.setFocus()

    def _browse_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select Directory", self._dir_edit.text())
        if path:
            self._dir_edit.setText(path)

    def _search_kwargs(self):
        return dict(
            recursive=self._recursive.isChecked(),
            include_glob=self._include_edit.text() or "*",
            exclude_glob=self._exclude_edit.text(),
            case_sensitive=self._match_case.isChecked(),
            whole_word=self._whole_word.isChecked(),
            use_regex=self._regex.isChecked(),
        )

    def _on_find_all(self):
        pattern = self._find_edit.text()
        root_dir = self._dir_edit.text()
        if not pattern or not root_dir:
            return
        hits = list(fif.search_files(root_dir, pattern, **self._search_kwargs()))
        self.hits_found.emit(hits)

    def _on_replace_all(self):
        pattern = self._find_edit.text()
        root_dir = self._dir_edit.text()
        if not pattern or not root_dir:
            return
        replacement = self._replace_edit.text()
        planned = fif.plan_replacements(
            root_dir, pattern, replacement, **self._search_kwargs()
        )
        if not planned:
            QMessageBox.information(self, "Replace All", "No matches found.")
            return
        total_hits = sum(len(r.hits) for r in planned)
        reply = QMessageBox.question(
            self,
            "Replace All",
            f"Replace {total_hits} occurrence(s) in {len(planned)} file(s)?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        fif.apply_replacements(planned)
        all_hits = [hit for r in planned for hit in r.hits]
        self.hits_found.emit(all_hits)
