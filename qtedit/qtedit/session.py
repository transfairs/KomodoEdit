"""Per-project open-tab session tracking -- no Qt.

Legacy Komodo doesn't store this in the .komodoproject XML itself; it's a
separate global pref (viewStateMRU) keyed by project URL (see the Projects
research in the plan doc). Mirrored here as a small sibling JSON file next
to prefs.json/toolbox/ instead of a pref -- same persistence idiom prefs.py
already uses, just its own file rather than growing PrefSet's schema for a
single feature.
"""
import json
import os

FILENAME = "sessions.json"


def _load_all(store_path):
    try:
        with open(store_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def load_session(store_path, project_path):
    """Returns (open_files, active_file) for `project_path`, or ([], None)
    if there's no recorded session yet."""
    entry = _load_all(store_path).get(project_path)
    if not entry:
        return [], None
    return entry.get("open_files", []), entry.get("active_file")


def save_session(store_path, project_path, open_files, active_file):
    sessions = _load_all(store_path)
    sessions[project_path] = {"open_files": open_files, "active_file": active_file}
    os.makedirs(os.path.dirname(store_path), exist_ok=True)
    with open(store_path, "w", encoding="utf-8") as f:
        json.dump(sessions, f, indent=2)
