"""Read-only access to Komodo's own compiled skin CSS.

The files under komodo12/ are a snapshot of what Komodo Edit 12.10 itself
uses: plain CSS from its skin (findbar.css) and what it produced from its LESS skin (src/chrome/komodo/skin/**/*.less): its
lessCache in the XRE profile dir, compiled against the profile colors.less
that Komodo generates from the active interface scheme ("Default"). Using
Komodo's own compiler output instead of re-compiling the LESS here means
every value (colors, paddings, heights, font sizes) is exactly what the
legacy UI renders with, no second LESS implementation involved.

The rules target XUL elements, so they can't be fed to Qt as-is. Instead
qss.py looks up individual values by Komodo's own selectors, e.g.
``rule("#komodo_main statusbar")["height"]``, and writes them into QSS for
the matching Qt widget.
"""
import os
import re

SNAPSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "komodo12")

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_LESS_VAR_RE = re.compile(r"^@([\w-]+)\s*:\s*([^;]+);", re.M)


def _normalize_selector(selector):
    return " ".join(selector.split())


def _skip_block(text, start):
    """Return the index just past the {...} block opening at/after start."""
    depth = 0
    for i in range(text.index("{", start), len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(text)


def _split_declarations(body):
    """Yield (property, value, important) from a declaration block."""
    for decl in body.split(";"):
        if ":" not in decl:
            continue
        prop, value = decl.split(":", 1)
        prop = prop.strip().lower()
        value = value.strip()
        important = value.endswith("!important")
        if important:
            value = value[: -len("!important")].strip()
        if prop:
            yield prop, value, important


class Stylesheet:
    """Selector -> {property: value} for one or more compiled CSS files.

    Comma-separated selector lists are split, so every individual selector
    can be looked up on its own. Later rules override earlier ones for the
    same selector, except that a non-!important value never overrides an
    !important one, i.e. the normal cascade restricted to identical
    selectors. Conditional/at-rule blocks (@media, @keyframes, @font-face)
    are skipped: they hold overlay-scrollbar and animation variants that
    have no Qt counterpart.
    """

    def __init__(self, paths):
        self._rules = {}
        self._important = {}
        for path in paths:
            with open(path, encoding="utf-8") as f:
                self._parse(_COMMENT_RE.sub("", f.read()))

    def _parse(self, text):
        pos = 0
        while True:
            brace = text.find("{", pos)
            if brace < 0:
                return
            prelude = text[pos:brace].strip()
            if prelude.startswith("@"):
                semicolon = text.find(";", pos)
                if 0 <= semicolon < brace:
                    # Statement at-rule (@namespace, @import): no block.
                    pos = semicolon + 1
                else:
                    pos = _skip_block(text, pos)
                continue
            end = text.find("}", brace)
            body = text[brace + 1 : end]
            for selector in prelude.split(","):
                selector = _normalize_selector(selector)
                if selector:
                    self._add(selector, body)
            pos = end + 1

    def _add(self, selector, body):
        rule = self._rules.setdefault(selector, {})
        important = self._important.setdefault(selector, set())
        for prop, value, is_important in _split_declarations(body):
            if prop in important and not is_important:
                continue
            rule[prop] = value
            if is_important:
                important.add(prop)

    def rule(self, selector):
        """All declarations for exactly this selector ({} if none)."""
        return dict(self._rules.get(_normalize_selector(selector), {}))

    def value(self, selector, prop, default=None):
        return self._rules.get(_normalize_selector(selector), {}).get(prop, default)

    def selectors(self, pattern):
        """Selectors matching a regex, for exploring the snapshot."""
        regex = re.compile(pattern)
        return [s for s in self._rules if regex.search(s)]


def load_colors(path=None):
    """Komodo's interface palette (@background, @selected, ...) as a dict.

    Read from the profile-generated colors.less rather than from the CSS,
    since these named roles are what a Qt QPalette needs.
    """
    path = path or os.path.join(SNAPSHOT_DIR, "colors.less")
    with open(path, encoding="utf-8") as f:
        text = _COMMENT_RE.sub("", f.read())
    return {name: value.strip() for name, value in _LESS_VAR_RE.findall(text)}


_default = None


def komodo_stylesheet():
    global _default
    if _default is None:
        _default = Stylesheet(
            os.path.join(SNAPSHOT_DIR, name)
            for name in (
                "global.css", "scrollbars.css", "breadcrumbs.css", "find2.css", "findbar.css",
            )
        )
    return _default
