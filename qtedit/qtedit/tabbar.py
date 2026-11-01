"""The editor tab strip, laid out like scrolltabs.xml#file-status-tab.

Qt's style sheet layer draws a tab's label with its own base-class code
whenever `QTabBar::tab` rules exist, never consulting the app style, and
puts 10px between icon and text where Komodo has 4px. So the style still
draws each tab's shape (background, the underline from the skin QSS) and
this bar draws icon and label itself, sized as Komodo's box:

    padding 6 | icon box 16 (14px icon, left) | 4 | label | 14 | close | 9 |

The close button stays a real widget (QTabBar places it); widths were
measured against docs/reference/komodo-12.10-editor.png.
"""
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QStyle, QStyleOptionTab, QStylePainter, QTabBar

from qtedit import icons
from qtedit.skin.css import komodo_stylesheet

PADDING = 6  # tab { padding: 2px 6px }
PADDING_V = 2
UNDERLINE = 2  # tab[selected] border-bottom, reserved on every tab
ICON_BOX = 16  # <xul:image width="16px" class="tab-icon">
ICON_SIZE = 14  # sdk/icons.js renders file icons at 14px
ICON_GAP = 4
CLOSE_GAP = 14  # label end to the close glyph's ink
CLOSE_SIZE = 16  # .tab-close-button font-size
CLOSE_TRAIL = 9  # close glyph's ink end to the tab's end


def _ink_columns(icon, size):
    """First and last column with ink in the icon's size x size pixmap."""
    image = icon.pixmap(size, size).toImage()
    columns = [x for x in range(image.width())
               if any(image.pixelColor(x, y).alpha() > 100 for y in range(image.height()))]
    return (columns[0], columns[-1]) if columns else (0, size - 1)


class KomodoTabBar(QTabBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        css = komodo_stylesheet()
        self._text_color = QColor(css.value("tab", "color", "#ffffff"))
        self._max_width = int(css.value('tab[type="file-tab"]', "max-width", "250px").rstrip("px"))
        self.close_icon = icons.glyph(icons.css_glyph(css.value(".tab-close-button:before", "content")),
                                      CLOSE_SIZE, QColor(css.value(".tab-close-button:before", "color")),
                                      CLOSE_SIZE)
        self._close_ink = _ink_columns(self.close_icon, CLOSE_SIZE)

    def tabSizeHint(self, index):
        height = super().tabSizeHint(index).height()
        width = (PADDING + ICON_BOX + ICON_GAP + self.fontMetrics().horizontalAdvance(self.tabText(index))
                 + self._label_to_close_box() + CLOSE_SIZE + self._close_box_trail())
        return QSize(min(width, self._max_width), height)

    def minimumTabSizeHint(self, index):
        return self.tabSizeHint(index)

    def _label_to_close_box(self):
        return CLOSE_GAP - self._close_ink[0]

    def _close_box_trail(self):
        # CLOSE_TRAIL counts from the ink's last column to the tab's last.
        return CLOSE_TRAIL - (CLOSE_SIZE - 1 - self._close_ink[1])

    @staticmethod
    def _content_box(rect):
        """XUL centres the tab's children in its content box: inside the
        vertical padding and above the underline."""
        return rect.adjusted(0, PADDING_V, 0, -(PADDING_V + UNDERLINE))

    def close_button_rect(self, index):
        """Where the close button goes inside tab `index`."""
        box = self._content_box(self.tabRect(index))
        x = box.right() + 1 - self._close_box_trail() - CLOSE_SIZE
        return QRect(x, box.top() + (box.height() - CLOSE_SIZE) // 2, CLOSE_SIZE, CLOSE_SIZE)

    def paintEvent(self, event):
        painter = QStylePainter(self)
        for index in range(self.count()):
            option = QStyleOptionTab()
            self.initStyleOption(option, index)
            # Shape only: background and the skin's underline.
            painter.drawControl(QStyle.ControlElement.CE_TabBarTabShape, option)
            self._paint_label(painter, index, option.rect)

    def _paint_label(self, painter: QPainter, index, tab_rect):
        rect = self._content_box(tab_rect)
        icon = self.tabIcon(index)
        x = rect.left() + PADDING
        if not icon.isNull():
            icon.paint(painter, QRect(x, rect.top() + (rect.height() - ICON_SIZE) // 2, ICON_SIZE, ICON_SIZE),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        x += ICON_BOX + ICON_GAP
        right = rect.right() + 1 - self._close_box_trail() - CLOSE_SIZE - self._label_to_close_box()
        text = self.fontMetrics().elidedText(self.tabText(index), Qt.TextElideMode.ElideRight, right - x)
        painter.setPen(self._text_color)
        painter.drawText(QRect(x, rect.top(), right - x, rect.height()),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)

    def tabLayoutChange(self):
        super().tabLayoutChange()
        self._place_close_buttons()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_close_buttons()

    def _place_close_buttons(self):
        for index in range(self.count()):
            button = self.tabButton(index, QTabBar.ButtonPosition.RightSide)
            if button is not None:
                button.setGeometry(self.close_button_rect(index))
