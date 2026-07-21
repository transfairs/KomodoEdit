"""Phase-0 spike: does a pyside6-scintilla ScintillaEdit widget render and
work in this environment (Wayland, Ubuntu 26.04)? Not meant to be kept —
throwaway validation script per the modernization plan."""
import sys

from PySide6.QtWidgets import QApplication, QMainWindow
from pyside6_scintilla import ScintillaEdit



SAMPLE = '''def greet(name):
    """Say hello."""
    print("Hello, " + name)


greet("KomodoEdit")
'''

# Minimal manual/container-style highlighting (SCLEX_CONTAINER-equivalent by
# hand): pyside6-scintilla exposes the raw SCI_* message API but not a
# Lexilla lexer factory, so "free" built-in lexers aren't available through
# this binding. Styling a fixed keyword range directly proves the styling
# pipeline works without depending on that.
STYLE_DEFAULT = 32
STYLE_KEYWORD = 1


def build_window():
    window = QMainWindow()
    window.setWindowTitle("KomodoEdit Qt spike")
    window.resize(800, 500)

    edit = ScintillaEdit(window)
    edit.styleClearAll()
    edit.styleSetFore(STYLE_DEFAULT, 0x202020)
    edit.styleSetFore(STYLE_KEYWORD, 0x0000A0)
    edit.styleSetBold(STYLE_KEYWORD, True)
    edit.setMarginWidthN(0, 40)

    edit.setText(SAMPLE)

    start = SAMPLE.index("def")
    edit.startStyling(start, 0)
    edit.setStyling(3, STYLE_KEYWORD)  # "def"

    window.setCentralWidget(edit)
    return window


def main():
    app = QApplication(sys.argv)
    window = build_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
