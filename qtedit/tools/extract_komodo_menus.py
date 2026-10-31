#!/usr/bin/env python3
"""Snapshot Komodo's main menubar into qtedit/qtedit/skin/komodo12/menus.json.

Dev-time tool, run against an installed Komodo (default ~/.komodo), not at
qtedit runtime. It reproduces what Gecko does when it builds komodo.xul's
menubar:

- the chrome registry: every chrome.manifest (also inside .xpi archives and
  jar: paths) maps chrome://<pkg>/content|locale/ URLs to files
- localization: DOCTYPE parameter entities pull in the en-US .dtd files and
  every &entity; is substituted
- overlays: <?xul-overlay?> processing instructions plus `overlay` manifest
  lines, merged by id with insertbefore/insertafter/position, recursively

The installed files are already preprocessed for Linux, so no #if handling
is needed. Shortcuts come from the keybinding scheme (Legacy.kkf by
default, matching the keybinding-scheme pref), keyed by command id, the way
ko.keybindings adds accelerator text to menu items at runtime.

    python3 qtedit/tools/extract_komodo_menus.py [--komodo ~/.komodo] [--scheme Legacy]
"""
import argparse
import html
import io
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

OUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "qtedit", "skin", "komodo12", "menus.json",
)
MASTER = "chrome://komodo/content/komodo.xul"
LOCALE = "en-US"

_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_ENTITY_DECL_RE = re.compile(
    r"<!ENTITY\s+(%\s+)?([\w.\-]+)\s+(?:SYSTEM\s+)?(\"[^\"]*\"|'[^']*')\s*>", re.S
)
_PARAM_REF_RE = re.compile(r"%([\w.\-]+);")
_QUOTED = r"(?:\"[^\"]*\"|'[^']*')"
_DOCTYPE_RE = re.compile(
    rf"<!DOCTYPE\s+[\w:]+\s*(?:(?:SYSTEM|PUBLIC\s+{_QUOTED})\s+({_QUOTED}))?\s*(?:\[(.*?)\])?\s*>",
    re.S,
)
_ENTITY_REF_RE = re.compile(r"&([\w.\-]+);")
_OVERLAY_PI_RE = re.compile(r"<\?xul-overlay\s+href=\"([^\"]+)\"\s*\?>")
_XML_BUILTINS = {"lt", "gt", "amp", "quot", "apos"}


class Location:
    """A directory on disk or a directory inside a zip archive."""

    def __init__(self, path, zip_file=None):
        self.path = path
        self.zip = zip_file

    def child(self, rel):
        if rel.startswith("jar:"):
            jar, _, inner = rel[4:].partition("!/")
            try:
                if self.zip is not None:
                    # A jar inside an .xpi: open it from the outer archive.
                    data = self.zip.read(self._join(jar).lstrip("/"))
                    return Location(inner, zipfile.ZipFile(io.BytesIO(data)))
                return Location(inner, zipfile.ZipFile(os.path.join(self.path, jar)))
            except (KeyError, OSError):
                # Broken package (the manifest names a jar that isn't
                # shipped); Gecko can't load from it either.
                return Location(os.path.join(self.path or "", "<missing>", jar), None)
        return Location(self._join(rel), self.zip)

    def _join(self, rel):
        if self.zip is not None:
            return (self.path.rstrip("/") + "/" + rel).lstrip("/") if self.path else rel
        return os.path.join(self.path, rel)

    def read(self, rel=""):
        target = self._join(rel) if rel else self.path
        if self.zip is not None:
            return self.zip.read(target.lstrip("/")).decode("utf-8")
        with open(target, encoding="utf-8") as f:
            return f.read()


class ChromeRegistry:
    def __init__(self, mozilla_dir):
        self.content = {}
        self.locale = {}
        self.overlays = {}  # target url -> [overlay url]
        chrome = os.path.join(mozilla_dir, "chrome")
        for name in sorted(os.listdir(chrome)):
            if name.endswith(".manifest"):
                self._load_manifest(Location(chrome), name)
        ext_dir = os.path.join(mozilla_dir, "extensions")
        for name in sorted(os.listdir(ext_dir)):
            full = os.path.join(ext_dir, name)
            if name.endswith(".xpi"):
                zf = zipfile.ZipFile(full)
                if "chrome.manifest" in zf.namelist():
                    self._load_manifest(Location("", zf), "chrome.manifest")
            elif os.path.isfile(os.path.join(full, "chrome.manifest")):
                self._load_manifest(Location(full), "chrome.manifest")

    def _load_manifest(self, base, name):
        try:
            text = base.read(name)
        except (OSError, KeyError):
            return
        manifest_dir = base.child(os.path.dirname(name)) if os.path.dirname(name) else base
        for line in text.splitlines():
            parts = line.split("#", 1)[0].split()
            if not parts:
                continue
            kind = parts[0]
            if kind == "manifest" and len(parts) > 1:
                self._load_manifest(manifest_dir, parts[1])
            elif kind == "content" and len(parts) >= 3:
                self.content.setdefault(parts[1], manifest_dir.child(parts[2]))
            elif kind == "locale" and len(parts) >= 4 and parts[2] == LOCALE:
                self.locale.setdefault(parts[1], manifest_dir.child(parts[3]))
            elif kind == "overlay" and len(parts) >= 3:
                self.overlays.setdefault(parts[1], []).append(parts[2])

    def read(self, url):
        match = re.match(r"chrome://([^/]+)/(content|locale|skin)/(.*)$", url)
        if not match:
            raise KeyError(url)
        pkg, kind, rest = match.groups()
        table = self.content if kind == "content" else self.locale
        if pkg not in table:
            raise KeyError(url)
        return table[pkg].read(rest)


def _unquote(value):
    return value[1:-1]


def _load_dtd(registry, url, entities, seen):
    if url in seen:
        return
    seen.add(url)
    try:
        text = _COMMENT_RE.sub("", registry.read(url))
    except (KeyError, OSError):
        return
    _parse_entities(registry, text, entities, seen)


def _parse_entities(registry, text, entities, seen):
    params = {}
    for is_param, name, value in _ENTITY_DECL_RE.findall(text):
        if is_param:
            params[name] = _unquote(value)
        else:
            entities.setdefault(name, _unquote(value))
    for ref in _PARAM_REF_RE.findall(text):
        if ref in params:
            _load_dtd(registry, params[ref], entities, seen)


def _resolve(value, entities, depth=0):
    if depth > 5:
        return value
    return _ENTITY_REF_RE.sub(
        lambda m: m.group(0) if m.group(1) in _XML_BUILTINS
        else _resolve(entities.get(m.group(1), m.group(1)), entities, depth + 1),
        value,
    )


def load_xul(registry, url):
    """Parse a XUL file with its entities substituted. Returns (root,
    overlay hrefs from <?xul-overlay?> PIs)."""
    text = registry.read(url)
    entities = {}
    seen = set()
    doctype = _DOCTYPE_RE.search(text)
    if doctype:
        system_url, subset = doctype.groups()
        if system_url:
            _load_dtd(registry, _unquote(system_url), entities, seen)
        if subset:
            _parse_entities(registry, _COMMENT_RE.sub("", subset), entities, seen)
        text = text[: doctype.start()] + text[doctype.end():]
    overlay_hrefs = _OVERLAY_PI_RE.findall(text)

    def substitute(match):
        name = match.group(1)
        if name in _XML_BUILTINS:
            return match.group(0)
        value = _resolve(entities.get(name, name), entities)
        return html.escape(html.unescape(value), quote=True)

    text = _ENTITY_REF_RE.sub(substitute, text)
    root = ET.fromstring(text)
    for elem in root.iter():
        if isinstance(elem.tag, str) and "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]
    return root, overlay_hrefs


class Document:
    """komodo.xul plus everything overlaid onto it."""

    def __init__(self, registry, url):
        self.registry = registry
        self.root, hrefs = load_xul(registry, url)
        self.ids = {}
        self.parents = {}
        self._index(self.root, None)
        self._applied = set()
        self._apply_overlays(url, hrefs)

    def _index(self, elem, parent):
        if parent is not None:
            self.parents[elem] = parent
        if elem.get("id"):
            self.ids.setdefault(elem.get("id"), elem)
        for child in elem:
            self._index(child, elem)

    def _apply_overlays(self, url, pi_hrefs):
        for href in list(pi_hrefs) + self.registry.overlays.get(url, []):
            if href in self._applied:
                continue
            self._applied.add(href)
            try:
                overlay, nested = load_xul(self.registry, href)
            except (KeyError, OSError, ET.ParseError) as exc:
                print(f"skipping overlay {href}: {exc}", file=sys.stderr)
                continue
            for top in overlay:
                target = self.ids.get(top.get("id") or "")
                if target is not None:
                    self._merge(target, top)
            self._apply_overlays(href, nested)

    def _merge(self, target, source):
        if source.get("removeelement") == "true":
            parent = self.parents.get(target)
            if parent is not None:
                parent.remove(target)
            return
        for key, value in source.attrib.items():
            if key != "id":
                target.set(key, value)
        for child in list(source):
            existing = self.ids.get(child.get("id") or "")
            if existing is not None:
                self._merge(existing, child)
                continue
            self._insert(target, child)
            self._index(child, target)

    def _insert(self, parent, child):
        children = list(parent)
        for attr, offset in (("insertbefore", 0), ("insertafter", 1)):
            for ref in (child.get(attr) or "").split(","):
                ref = ref.strip()
                for i, sibling in enumerate(children):
                    if ref and sibling.get("id") == ref:
                        parent.insert(i + offset, child)
                        return
        position = child.get("position")
        if position and position.isdigit():
            parent.insert(max(0, int(position) - 1), child)
            return
        parent.append(child)


def load_keybindings(path):
    bindings = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 3 and parts[0] == "binding":
                # First binding wins: that's the one Komodo shows as accel text.
                bindings.setdefault(parts[1], " ".join(parts[2:]))
    return bindings


def _command_of(elem):
    for attr in ("observes", "command"):
        if elem.get(attr):
            return elem.get(attr)
    match = re.search(r"doCommand\(['\"](cmd_\w+)['\"]\)", elem.get("oncommand", ""))
    return match.group(1) if match else None


def serialize(elem, bindings):
    tag = elem.tag
    if tag == "menuseparator":
        return {"type": "separator", "id": elem.get("id")}
    if tag not in ("menu", "menuitem"):
        return None
    node = {"type": tag, "id": elem.get("id"), "label": elem.get("label", "")}
    if elem.get("accesskey"):
        node["accesskey"] = elem.get("accesskey")
    if elem.get("hidden") == "true" or elem.get("collapsed") == "true":
        node["hidden"] = True
    if tag == "menuitem":
        command = _command_of(elem)
        if command:
            node["command"] = command
            if command in bindings:
                node["shortcut"] = bindings[command]
        if elem.get("type") in ("checkbox", "radio"):
            node["checkable"] = elem.get("type")
        if elem.get("oncommand") and not command:
            node["oncommand"] = elem.get("oncommand").strip()
        return node
    children = []
    popup = next((c for c in elem if c.tag == "menupopup"), None)
    for child in (popup if popup is not None else []):
        item = serialize(child, bindings)
        if item is not None:
            children.append(item)
    node["children"] = children
    if popup is not None and popup.get("id"):
        node["popup_id"] = popup.get("id")
    return node


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--komodo", default=os.path.expanduser("~/.komodo"))
    parser.add_argument("--scheme", default="Legacy")
    parser.add_argument("--out", default=OUT_PATH)
    args = parser.parse_args()

    registry = ChromeRegistry(os.path.join(args.komodo, "lib", "mozilla"))
    doc = Document(registry, MASTER)
    menubar = doc.ids.get("menubar_main")
    if menubar is None:
        sys.exit("menubar_main not found")
    bindings = load_keybindings(
        os.path.join(args.komodo, "lib", "support", "schemes", f"{args.scheme}.kkf")
    )
    menus = [m for m in (serialize(c, bindings) for c in menubar) if m]
    snapshot = {
        "source": f"{args.komodo} (komodo.xul + overlays), keybinding scheme {args.scheme}",
        "menus": menus,
        # Every command's first binding, for commands without a menu item.
        "bindings": dict(sorted(bindings.items())),
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=1, ensure_ascii=False)
        f.write("\n")

    def count(nodes):
        return sum(1 + count(n.get("children", [])) for n in nodes)

    print(f"wrote {args.out}: {len(menus)} menus, {count(menus)} entries")


if __name__ == "__main__":
    main()
