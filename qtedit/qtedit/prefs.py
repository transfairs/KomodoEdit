"""Minimal, Qt-native preferences store.

Komodo's legacy koPrefs.py (src/prefs/koPrefs.py) is a typed key/value store
per preference-set node, with nodes forming an inheritance chain (global
defaults <- user prefs <- project prefs) and change notification via
nsIObserverService, persisted as XML with a pickle fast-cache. None of that
machinery is worth porting: Python/JSON already carry str/int/float/bool
natively (Komodo's explicit type tagging was an XPCOM necessity), and Qt
signals are a more natural fit than an XPCOM observer service. This keeps
only the two ideas actually worth keeping -- a typed store and a parent
inheritance chain -- as a small, from-scratch implementation.
"""
import json
import os

from PySide6.QtCore import QObject, QStandardPaths, Signal

# v1 scope: just enough real, visible settings to prove the architecture,
# not a reproduction of Komodo's ~461 legacy pref names.
DEFAULT_PREFS = {
    "useTabs": True,
    "tabWidth": 8,
    "indentWidth": 4,
}


def _prefs_file_path():
    config_dir = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppConfigLocation
    )
    return os.path.join(config_dir, "prefs.json")


class PrefSet(QObject):
    """A typed key/value store. `parent_prefs`, if given, forms an
    inheritance chain: get() falls through to it when a name isn't set
    locally -- the same role Komodo's global-to-project prefset chain
    played, minus the XPCOM. Not wired to a project level yet (nothing to
    inherit from besides the global instance), but get()/set() already
    support it so Projects won't need a redesign here later."""

    changed = Signal(str)

    def __init__(self, parent_prefs=None, parent=None):
        super().__init__(parent)
        self.parent_prefs = parent_prefs
        self._values = {}

    def get(self, name, default=None):
        if name in self._values:
            return self._values[name]
        if self.parent_prefs is not None:
            return self.parent_prefs.get(name, default)
        return default

    def set(self, name, value):
        if self._values.get(name) == value:
            return
        self._values[name] = value
        self.changed.emit(name)

    def has_local(self, name):
        return name in self._values

    def as_dict(self):
        return dict(self._values)


class GlobalPrefSet(PrefSet):
    """The root PrefSet: seeded with DEFAULT_PREFS, persisted to a JSON file
    under the platform's standard config directory, saved on every change
    (the file is tiny, so there's no need for Komodo's pickle-cache trick to
    avoid a full parse on next launch)."""

    def __init__(self, path=None):
        super().__init__(parent_prefs=None)
        self._path = path or _prefs_file_path()
        self._values = dict(DEFAULT_PREFS)
        self._load()
        self.changed.connect(self._save)

    def _load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except (OSError, ValueError):
            return
        if isinstance(saved, dict):
            self._values.update(saved)

    def _save(self, _name=None):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._values, f, indent=2, sort_keys=True)


_global_prefs = None


def get_global_prefs():
    global _global_prefs
    if _global_prefs is None:
        _global_prefs = GlobalPrefSet()
    return _global_prefs
