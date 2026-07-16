"""Pure project data model -- no Qt, no XPCOM.

Format reference (not ported, just spec-compatible for the fields used
here): Komodo's legacy `.komodoproject` XML files, kpf_version 5 (see
src/samples/sample_project.p.komodoproject for a real minimal example, and
src/projects/koProject.p.py's `_serializeHeader` for the attribute layout
richer real-world .kpf fixtures use -- `<file url="relative/path"
name="..">`/`<folder url="relative/path/" name="..">...</folder>`, relative
URLs, plus an `<preference-set idref="...">` sibling). Komodo's own
`koProject.p.py` (~1981 LOC) mutates live XPCOM `koIPart` objects inline
while SAX-parsing and has no separable pure-logic core -- this is a
from-scratch reimplementation against a plain XML tree
(xml.etree.ElementTree), not a port.

Deliberately not implemented here (see plan doc's Projects-MVP section):
applying the embedded `<preference-set>` to the active editor prefs
(parsed/round-tripped losslessly but otherwise inert), continuous
live-folder import/sync (only a one-shot snapshot import), project-scoped
toolbox tools (`.komodotools/`, a Toolbox-module extension).
"""
import os
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

PROJECT_EXTENSION = ".komodoproject"
KPF_VERSION = "5"

# One-shot snapshot import skips these -- same spirit as the
# import_exclude_matches defaults in the real sample_project.p.komodoproject,
# just as a fixed list rather than configurable glob patterns.
IMPORT_SKIP_NAMES = {
    ".git", ".hg", ".bzr", ".svn", "__pycache__", "node_modules",
    ".DS_Store", ".komodotools",
}
IMPORT_SKIP_SUFFIXES = (".pyc", ".pyo", "~", ".bak", ".tmp")


@dataclass
class ProjectFile:
    name: str
    url: str  # path relative to the project file's directory


@dataclass
class ProjectFolder:
    name: str
    url: str = ""  # relative disk path for an imported folder; "" for a virtual group
    folders: list = field(default_factory=list)  # list[ProjectFolder]
    files: list = field(default_factory=list)  # list[ProjectFile]


@dataclass
class Project:
    path: str  # absolute path to the .komodoproject file
    name: str
    id: str
    folders: list = field(default_factory=list)  # list[ProjectFolder]
    files: list = field(default_factory=list)  # list[ProjectFile]
    # Raw <preference-set> child elements, kept only for lossless round-trip
    # -- see module docstring, not applied to the active editor prefs yet.
    raw_prefs: dict = field(default_factory=dict)

    @property
    def base_dir(self):
        return os.path.dirname(self.path)


def create_project(path, name):
    project = Project(path=path, name=name, id=str(uuid.uuid4()))
    save_project(project)
    return project


def _parse_folder(elem, base_dir):
    folder = ProjectFolder(name=elem.get("name", ""), url=elem.get("url", ""))
    for child in elem:
        if child.tag == "file":
            folder.files.append(
                ProjectFile(name=child.get("name", ""), url=child.get("url", ""))
            )
        elif child.tag == "folder":
            folder.folders.append(_parse_folder(child, base_dir))
    return folder


def load_project(path):
    tree = ET.parse(path)
    root = tree.getroot()
    project = Project(
        path=path,
        name=root.get("name", os.path.basename(path)),
        id=root.get("id", str(uuid.uuid4())),
    )
    for child in root:
        if child.tag == "preference-set":
            project.raw_prefs = {
                pref.get("id"): (pref.tag, pref.text or "") for pref in child
            }
        elif child.tag == "file":
            project.files.append(
                ProjectFile(name=child.get("name", ""), url=child.get("url", ""))
            )
        elif child.tag == "folder":
            project.folders.append(_parse_folder(child, project.base_dir))
    return project


def _write_folder(parent_elem, folder):
    folder_elem = ET.SubElement(
        parent_elem, "folder", {"name": folder.name, "url": folder.url}
    )
    for sub in folder.folders:
        _write_folder(folder_elem, sub)
    for file in folder.files:
        ET.SubElement(folder_elem, "file", {"name": file.name, "url": file.url})


def save_project(project):
    root = ET.Element(
        "project", {"id": project.id, "kpf_version": KPF_VERSION, "name": project.name}
    )
    if project.raw_prefs:
        prefset_elem = ET.SubElement(root, "preference-set", {"idref": project.id})
        for pref_id, (tag, text) in project.raw_prefs.items():
            pref_elem = ET.SubElement(prefset_elem, tag, {"id": pref_id})
            pref_elem.text = text
    for folder in project.folders:
        _write_folder(root, folder)
    for file in project.files:
        ET.SubElement(root, "file", {"name": file.name, "url": file.url})

    ET.indent(root, space="  ")
    tree = ET.ElementTree(root)
    with open(project.path, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(b"<!-- Komodo Project File - DO NOT EDIT -->\n")
        tree.write(f, encoding="utf-8")


def add_file(project, abs_path):
    rel = os.path.relpath(abs_path, project.base_dir)
    project.files.append(ProjectFile(name=os.path.basename(abs_path), url=rel))
    save_project(project)


def add_group(project, name):
    project.folders.append(ProjectFolder(name=name))
    save_project(project)


def _should_skip(name):
    if name in IMPORT_SKIP_NAMES:
        return True
    return any(name.endswith(suffix) for suffix in IMPORT_SKIP_SUFFIXES)


def _snapshot_folder(abs_dir, base_dir):
    folder = ProjectFolder(
        name=os.path.basename(abs_dir),
        url=os.path.relpath(abs_dir, base_dir) + "/",
    )
    for entry in sorted(os.listdir(abs_dir)):
        if _should_skip(entry):
            continue
        full_path = os.path.join(abs_dir, entry)
        if os.path.isdir(full_path):
            folder.folders.append(_snapshot_folder(full_path, base_dir))
        else:
            folder.files.append(
                ProjectFile(name=entry, url=os.path.relpath(full_path, base_dir))
            )
    return folder


def import_folder_snapshot(project, abs_dir):
    """One-shot recursive import of an existing directory's contents as
    explicit project members -- not a live/continuously-synced folder, see
    module docstring."""
    project.folders.append(_snapshot_folder(abs_dir, project.base_dir))
    save_project(project)


def remove_node(project, node):
    """Remove a ProjectFile/ProjectFolder from wherever it lives in the
    tree (top level or nested inside a folder). No-op if not found."""
    if _remove_from(project.files, project.folders, node):
        save_project(project)


def _remove_from(files, folders, node):
    # Identity comparison, not `in`/`.remove()` (dataclass `==` is by value,
    # and two distinct nodes can have identical name+url).
    for i, f in enumerate(files):
        if f is node:
            del files[i]
            return True
    for i, sub in enumerate(folders):
        if sub is node:
            del folders[i]
            return True
        if _remove_from(sub.files, sub.folders, node):
            return True
    return False
