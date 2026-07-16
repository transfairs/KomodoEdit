"""Pure multi-file search/replace logic -- no Qt, no XPCOM.

Komodo's legacy multi-file engine (src/find/findlib2.py, ~1822 LOC) is
actually XPCOM-free pure Python 2 (os/re/glob/fnmatch/codecs/cPickle only)
-- unlike Toolbox/Projects it would be technically separable. Kept
consistent with the rest of this rewrite anyway (see e.g. the UDL luddite
compiler, which also stays a Python-2-only dev-time tool rather than being
bridged): the actual search/replace algorithm here is simple enough
(os.walk + fnmatch + re) that a clean Python 3 rewrite is less work and
less risk than a second Python-2-subprocess bridge (which codeintel2 needs
only because of its much deeper language-intelligence logic).

Legacy's regex dialect for multi-file search is already plain Python `re`
(findlib2.py's regex_info_from_str), not Scintilla's own dialect or PCRE --
so this module's use of `re` directly is already format-compatible, no
translation layer needed.
"""
import fnmatch
import os
import re
from dataclasses import dataclass, field

# Simple heuristics, not Komodo's real encoding-detection machinery: a
# fixed size cap and a null-byte sniff on the first chunk are enough to
# keep an MVP multi-file search fast and avoid choking on binaries.
MAX_FILE_SIZE = 5 * 1024 * 1024
SNIFF_SIZE = 1024


@dataclass
class FileHit:
    path: str
    line_no: int  # 1-based, matches editor gotoLine's 0-based line minus 1 at call site
    column: int  # 0-based character offset into the line
    line_text: str
    match_start: int
    match_end: int


@dataclass
class FileReplacement:
    path: str
    hits: list  # list[FileHit]
    new_content: str


def _is_binary(path):
    try:
        with open(path, "rb") as f:
            chunk = f.read(SNIFF_SIZE)
    except OSError:
        return True
    return b"\x00" in chunk


def _compile_pattern(pattern, case_sensitive, whole_word, use_regex):
    text = pattern if use_regex else re.escape(pattern)
    if whole_word:
        text = rf"\b{text}\b"
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(text, flags)


def _iter_paths(root_dir, recursive, include_glob, exclude_glob):
    include_glob = include_glob or "*"
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for name in sorted(filenames):
            if not fnmatch.fnmatch(name, include_glob):
                continue
            if exclude_glob and fnmatch.fnmatch(name, exclude_glob):
                continue
            yield os.path.join(dirpath, name)
        if not recursive:
            dirnames[:] = []
        else:
            dirnames.sort()


def _read_text(path):
    if os.path.getsize(path) > MAX_FILE_SIZE or _is_binary(path):
        return None
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def search_files(
    root_dir,
    pattern,
    *,
    recursive=True,
    include_glob="*",
    exclude_glob="",
    case_sensitive=False,
    whole_word=False,
    use_regex=False,
):
    """Yield a FileHit for every match of `pattern` under `root_dir`."""
    if not pattern:
        return
    regex = _compile_pattern(pattern, case_sensitive, whole_word, use_regex)
    for path in _iter_paths(root_dir, recursive, include_glob, exclude_glob):
        text = _read_text(path)
        if text is None:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            for m in regex.finditer(line):
                yield FileHit(
                    path=path,
                    line_no=line_no,
                    column=m.start(),
                    line_text=line,
                    match_start=m.start(),
                    match_end=m.end(),
                )


def plan_replacements(
    root_dir,
    pattern,
    replacement,
    *,
    recursive=True,
    include_glob="*",
    exclude_glob="",
    case_sensitive=False,
    whole_word=False,
    use_regex=False,
):
    """Build the list of files that would change, without writing anything
    -- callers should confirm with the user before calling
    apply_replacements() on the result."""
    if not pattern:
        return []
    regex = _compile_pattern(pattern, case_sensitive, whole_word, use_regex)
    repl = replacement if use_regex else replacement.replace("\\", "\\\\")
    results = []
    for path in _iter_paths(root_dir, recursive, include_glob, exclude_glob):
        text = _read_text(path)
        if text is None:
            continue
        hits = []
        lines = text.splitlines(keepends=True)
        for line_no, line in enumerate(lines, start=1):
            for m in regex.finditer(line):
                hits.append(
                    FileHit(
                        path=path,
                        line_no=line_no,
                        column=m.start(),
                        line_text=line.rstrip("\n"),
                        match_start=m.start(),
                        match_end=m.end(),
                    )
                )
        if not hits:
            continue
        new_content = regex.sub(repl, text)
        results.append(FileReplacement(path=path, hits=hits, new_content=new_content))
    return results


def apply_replacements(replacements):
    """Write each FileReplacement's new_content to disk. Separate from
    plan_replacements() so the caller can show a confirmation dialog with
    the planned changes in between."""
    for repl in replacements:
        with open(repl.path, "w", encoding="utf-8") as f:
            f.write(repl.new_content)
