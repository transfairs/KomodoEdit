import os
import sys

# Must be set before Qt's platform integration initializes (import time is
# safest), not just before QApplication() -- see snapcraft.yaml for why:
# without QT_WAYLAND_DECORATION there's no titlebar decoration plugin
# active under Wayland at all (no min/max/close buttons), and without
# QT_QPA_PLATFORMTHEME Qt never reads the desktop's dark-mode/theme
# setting. setdefault() so a real env var still wins if someone wants to
# override these.
os.environ.setdefault("QT_WAYLAND_DECORATION", "adwaita")
os.environ.setdefault("QT_QPA_PLATFORMTHEME", "gtk3")

from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from qtedit.main_window import APP_ICON_PATH, MainWindow

# Only relevant for a direct venv launch (`python -m qtedit`) -- the packed
# Snap doesn't need this, snapcraft generates a real .desktop entry from
# snapcraft.yaml's apps/icon fields automatically. Without *some* local
# .desktop file, Wayland/GNOME has nothing to resolve a Dock/App-Grid icon
# from (that resolution goes through the desktop entry matched by app_id,
# not the QIcon set at runtime -- see the Themes/Skinning phase's result in
# the plan doc for the investigation behind this).
DESKTOP_FILE_ID = "qtedit-dev"


def _ensure_desktop_file():
    apps_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "applications")
    os.makedirs(apps_dir, exist_ok=True)
    desktop_path = os.path.join(apps_dir, f"{DESKTOP_FILE_ID}.desktop")
    # sys.executable is this venv's own interpreter -- rewritten on every
    # start rather than written once, since the venv path can change (e.g.
    # recreated at a different location) and a stale Exec= would silently
    # launch the wrong (or a nonexistent) interpreter from the Dock.
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=KomodoEdit (Qt, dev)\n"
        f"Exec={sys.executable} -m qtedit %f\n"
        f"Icon={APP_ICON_PATH}\n"
        "Terminal=false\n"
        "Categories=Development;TextEditor;\n"
    )
    with open(desktop_path, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    _ensure_desktop_file()
    app = QApplication(sys.argv)
    # QStandardPaths.AppConfigLocation (used by prefs.py) is keyed off
    # applicationName; without this it falls back to argv[0]'s basename,
    # e.g. "-c" or "__main__" depending on how the app was launched.
    app.setApplicationName("qtedit")
    app.setOrganizationName("qtedit")
    # Matches DESKTOP_FILE_ID above so Wayland/GNOME can resolve this
    # running instance back to the .desktop file _ensure_desktop_file()
    # just wrote (Dock/App-Grid icon resolution, see its docstring).
    QGuiApplication.setDesktopFileName(DESKTOP_FILE_ID)
    # Some window managers use the application-level icon (taskbar, Alt-Tab,
    # desktop-file association) rather than the per-window one set in
    # MainWindow -- set both.
    if os.path.isfile(APP_ICON_PATH):
        app.setWindowIcon(QIcon(APP_ICON_PATH))
    project_dir = sys.argv[1] if len(sys.argv) > 1 else None
    window = MainWindow(project_dir)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
