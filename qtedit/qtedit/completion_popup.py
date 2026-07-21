from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QListWidget, QListWidgetItem


class CompletionPopup(QListWidget):
    """Minimal completion list: a floating overlay near the caret. Accepting
    an item emits `accepted(name)`; anything else (Escape, click outside,
    losing focus) just closes it -- callers don't need to distinguish.

    This is a plain child widget of the main window, not a separate
    Qt.WindowType.Popup top-level window -- Wayland's xdg_popup protocol
    requires a *recent* input grab (tied to the keypress that triggered
    it) to let a popup surface actually appear, and codeintel's
    scan/trigger/eval round-trip is async and can take several real
    seconds on a cold cache. By the time show_completions() runs, that
    grab can already be stale, so the popup silently fails to show (or
    closes itself instantly) -- confirmed via real user testing, not
    guessed. A plain child widget, manually raised/positioned/focused
    within the already-focused main window, never creates a new Wayland
    surface at all, so this class of timing issue doesn't apply.
    """

    accepted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.Box)
        self.setStyleSheet(
            "QListWidget { border: 1px solid palette(mid); }"
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.itemActivated.connect(self._accept_item)
        self.hide()

    def show_completions(self, cplns, pos):
        """`pos` is in this widget's parent's coordinate system (see
        main_window._on_eval, which maps the caret's screen position back
        into the main window rather than leaving it in global/screen
        coordinates -- this widget is a child, not a top-level window)."""
        self.clear()
        for kind, name in cplns:
            item = QListWidgetItem(name)
            item.setToolTip(kind)
            self.addItem(item)
        if self.count() == 0:
            return
        self.setCurrentRow(0)
        self.move(pos)
        self.resize(260, min(200, self.sizeHintForRow(0) * min(self.count(), 8) + 6))
        self.show()
        self.raise_()
        self.setFocus()

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

    def focusOutEvent(self, event):
        # Replaces Qt.WindowType.Popup's automatic "closes when it loses
        # the input grab" behavior -- clicking elsewhere in the same
        # window (e.g. back into the editor) moves Qt's internal focus
        # away from this widget, which is enough to detect here since
        # everything now lives in one real window.
        self.close()
        super().focusOutEvent(event)

    def _accept_item(self, item):
        self.accepted.emit(item.text())
        self.close()
