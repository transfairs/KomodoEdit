#!/usr/bin/env python3
"""Snapshot Komodo's language names and comment delimiters for qtedit.

Komodo defines `commentDelimiterInfo` as a class attribute on its language
classes (src/languages, src/udl/skel, src/modules), inheriting it through
base classes (Python3 gets Python's from KoPythonCommonLanguage). The files
are Python 2, so instead of importing them this scans class headers and the
two attributes we need, evaluates the dict literals and resolves
inheritance by class name.

    python3 tools/extract_komodo_languages.py [KOMODO_SRC] > qtedit/skin/komodo12/languages.json
"""
import ast
import json
import os
import re
import sys

CLASS_RE = re.compile(r"^class\s+(\w+)\s*(?:\(([^)]*)\))?\s*:", re.M)
NAME_RE = re.compile(r"^    name\s*=\s*([\"'])(.+?)\1", re.M)
COMMENT_RE = re.compile(r"^    commentDelimiterInfo\s*=\s*", re.M)

# Test fixtures and the SDK template aren't real languages.
SKIP_DIRS = ("/test/", "/sdk/")


def _balanced(text, start):
    """The {...} literal starting at text[start]."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise ValueError("unbalanced dict literal")


def _strip_comments(literal):
    return "\n".join(re.sub(r"#[^\"'\n]*$", "", line) for line in literal.splitlines())


def scan_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    headers = list(CLASS_RE.finditer(text))
    classes = {}
    for index, header in enumerate(headers):
        body_end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        body = text[header.end():body_end]
        bases = [b.strip().split(".")[-1] for b in (header.group(2) or "").split(",") if b.strip()]
        info = {"bases": bases}
        name = NAME_RE.search(body)
        if name:
            info["name"] = name.group(2)
        comment = COMMENT_RE.search(body)
        if comment:
            literal = _balanced(body, body.index("{", comment.end()))
            info["comment"] = ast.literal_eval(_strip_comments(literal))
        classes[header.group(1)] = info
    return classes


def collect(src):
    classes = {}
    for root, _dirs, files in os.walk(src):
        if any(skip in root + "/" for skip in SKIP_DIRS):
            continue
        for filename in sorted(files):
            if filename.endswith(".py") and "Language" in filename:
                classes.update(scan_file(os.path.join(root, filename)))
    return classes


def resolve(classes, class_name, attr, seen=()):
    info = classes.get(class_name)
    if info is None or class_name in seen:
        return None
    if attr in info:
        return info[attr]
    for base in info["bases"]:
        value = resolve(classes, base, attr, seen + (class_name,))
        if value is not None:
            return value
    return None


def _jsonable(info):
    """Tuples (block delimiter pairs) become lists in JSON."""
    return {key: [list(v) if isinstance(v, tuple) else v for v in value]
            if isinstance(value, list) else value
            for key, value in info.items()}


def main(argv):
    src = argv[1] if len(argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", "src")
    classes = collect(os.path.abspath(src))
    languages = {}
    for class_name, info in classes.items():
        if "name" not in info:
            continue
        comment = resolve(classes, class_name, "comment")
        if comment:
            languages[info["name"]] = _jsonable(comment)
    names = sorted({info["name"] for info in classes.values() if "name" in info})
    json.dump({"source": "Komodo 12.10 src/ language classes", "names": names, "comments": languages},
              sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main(sys.argv)
