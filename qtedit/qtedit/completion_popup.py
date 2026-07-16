from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem


class CompletionPopup(QListWidget):
    """Minimal completion list: a frameless popup near the caret. Accepting
    an item emits `accepted(name)`; anything else (Escape, click outside,
    losing focus) just closes it -- callers don't need to distinguish."""

    accepted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.itemActivated.connect(self._accept_item)

    def show_completions(self, cplns, global_pos):
        self.clear()
        for kind, name in cplns:
            item = QListWidgetItem(name)
            item.setToolTip(kind)
            self.addItem(item)
        if self.count() == 0:
            return
        self.setCurrentRow(0)
        self.move(global_pos)
        self.resize(260, min(200, self.sizeHintForRow(0) * min(self.count(), 8) + 6))
        self.show()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
            item = self.currentItem()
            if item is not None:
                self._accept_item(item)
            return
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def _accept_item(self, item):
        self.accepted.emit(item.text())
        self.close()
