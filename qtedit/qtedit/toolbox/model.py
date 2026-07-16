"""Pure toolbox data model -- no Qt, no XPCOM.

Format reference (not ported, just spec-compatible for the fields used
here): Komodo's legacy `.komodotool` JSON files, e.g.
src/samples/tools/Sample_Snippet_-_Double_Click_to_Insert.komodotool
(type "snippet") and src/samples/tools/Find_in_Files.komodotool.std (type
"command"). Both real-world samples carry many more fields than used here
(interactive `[[%ask:...]]`/`%(ask:...)` prompts, snippet cursor-position
markup, regex-parsed command output, per-tool keyboard shortcuts) -- this
is deliberately a small subset: `name` + `value[0]` for snippets, plus
`cwd` for commands, nothing else.
"""
import json
import os
from dataclasses import dataclass, field

ITEM_EXTENSION = ".komodotool"
SNIPPET = "snippet"
COMMAND = "command"


@dataclass
class ToolboxItem:
    name: str
    type: str  # SNIPPET or COMMAND
    value: str
    cwd: str = ""
    path: str = ""


@dataclass
class ToolboxFolder:
    name: str
    path: str
    folders: list = field(default_factory=list)  # list[ToolboxFolder]
    items: list = field(default_factory=list)  # list[ToolboxItem]


_DEFAULT_ITEMS = [
    (
        "Hello Snippet" + ITEM_EXTENSION,
        {"name": "Hello Snippet", "type": SNIPPET, "value": ["Hello, world!\n"]},
    ),
    (
        "List Directory" + ITEM_EXTENSION,
        {"name": "List Directory", "type": COMMAND, "value": ["ls -la"], "cwd": ""},
    ),
]


def ensure_default_toolbox(root_path):
    """Seed a couple of example items on first run (root_path doesn't exist
    yet) so the toolbox isn't empty and both item types are visible right
    away. No-op on every later run."""
    if os.path.isdir(root_path):
        return
    os.makedirs(root_path, exist_ok=True)
    for filename, data in _DEFAULT_ITEMS:
        with open(os.path.join(root_path, filename), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


def _parse_item(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    item_type = data.get("type")
    if item_type not in (SNIPPET, COMMAND):
        return None
    value_list = data.get("value") or [""]
    return ToolboxItem(
        name=data.get("name", os.path.basename(path)),
        type=item_type,
        value=value_list[0] if value_list else "",
        cwd=data.get("cwd", ""),
        path=path,
    )


def scan_toolbox(root_path):
    """Walk `root_path` into a ToolboxFolder tree. Only bare `.komodotool`
    files are read as items -- not the `.win`/`.std` platform-variant
    siblings Komodo also uses, matching its own preference for the base
    file when present."""
    folder = ToolboxFolder(name=os.path.basename(root_path) or root_path, path=root_path)
    if not os.path.isdir(root_path):
        return folder
    for entry in sorted(os.listdir(root_path)):
        full_path = os.path.join(root_path, entry)
        if os.path.isdir(full_path):
            folder.folders.append(scan_toolbox(full_path))
        elif entry.endswith(ITEM_EXTENSION):
            item = _parse_item(full_path)
            if item is not None:
                folder.items.append(item)
    return folder


def create_item(folder_path, name, item_type, value="", cwd=""):
    """Write a new `.komodotool` file and return its path."""
    data = {"name": name, "type": item_type, "value": [value]}
    if item_type == COMMAND:
        data["cwd"] = cwd
    path = os.path.join(folder_path, name + ITEM_EXTENSION)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return path


def update_item(path, name, item_type, value, cwd=""):
    """Overwrite an existing item file's content in place -- the path/
    filename stays the same, renaming isn't supported here."""
    data = {"name": name, "type": item_type, "value": [value]}
    if item_type == COMMAND:
        data["cwd"] = cwd
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def create_folder(parent_path, name):
    path = os.path.join(parent_path, name)
    os.makedirs(path, exist_ok=True)
    return path


def delete_path(path):
    """Remove an item file or an empty folder. Raises OSError for a
    non-empty folder rather than silently deleting its contents -- callers
    should surface that to the user instead of forcing a recursive delete."""
    if os.path.isdir(path):
        os.rmdir(path)
    else:
        os.remove(path)
