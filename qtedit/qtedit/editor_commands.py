"""Komodo's Code and Navigation menu commands, ported to ScintillaEdit.

The bodies follow Komodo 12.10's own implementations so behaviour (which
lines get touched, where the selection ends up, one undo step per command)
matches:

- comment/uncomment: KoCommenterLanguageService in
  src/languages/koLanguageServiceBase.py, with the per-language
  commentDelimiterInfo snapshot in skin/komodo12/languages.json
  (tools/extract_komodo_languages.py)
- case/hex conversion, tabify, fold jumps, scrolling:
  src/editor/koLanguageCommandHandler.p.py
- join, trailing whitespace: src/SciMoz/koScintillaController.p.py
- bookmarks: src/chrome/komodo/content/editor.js and markers.js

Only stream selections are handled; Komodo's rectangular-selection
variants are not ported yet. Scintilla positions are UTF-8 byte offsets,
so all lengths handed back to it go through _byte_len.
"""
import ctypes
import json
import os
import re

from PySide6.QtGui import QImage
from pyside6_scintilla import Scintilla

SKIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skin", "komodo12")
LANGUAGES_PATH = os.path.join(SKIN_DIR, "languages.json")
BOOKMARK_XPM_PATH = os.path.join(SKIN_DIR, "bookmark.xpm")

# ko.markers (markers.js): MARKNUM_BOOKMARK, below the fold markers 25-31.
MARKNUM_BOOKMARK = 6

# Scintilla fold level bits (SC_FOLDLEVEL*).
FOLDLEVELBASE = 0x400
FOLDLEVELNUMBERMASK = 0x0FFF
FOLDLEVELHEADERFLAG = 0x2000

_comment_info = None


def comment_delimiters(names):
    """Komodo's commentDelimiterInfo for the first of `names` (language
    name, then lexer aliases) it knows, else None."""
    global _comment_info
    if _comment_info is None:
        with open(LANGUAGES_PATH, encoding="utf-8") as f:
            _comment_info = json.load(f)["comments"]
        _comment_info.update({k.lower(): v for k, v in list(_comment_info.items())})
    for name in names:
        if name and (name in _comment_info or name.lower() in _comment_info):
            return _comment_info.get(name) or _comment_info[name.lower()]
    return None


def _byte_len(text):
    return len(text.encode("utf-8"))


def _text(ed, start, end):
    return bytes(ed.textRange(start, end)).decode("utf-8", errors="replace")


def _replace(ed, start, end, text):
    ed.setTargetRange(start, end)
    ed.replaceTarget(_byte_len(text), text)


def _split_lines(text):
    """'a\\nb\\r\\nc' -> [('a', '\\n'), ('b', '\\r\\n'), ('c', '')]"""
    parts = re.split("(\r\n|\n|\r)", text)
    return [(parts[i], parts[i + 1] if i + 1 < len(parts) else "") for i in range(0, len(parts), 2)]


def _delimiter_pair(delimiter):
    """A 'line' entry is a prefix, or a [prefix, suffix] pair when a
    block-only language comments line-wise."""
    if isinstance(delimiter, (list, tuple)):
        return delimiter[0], delimiter[1]
    return delimiter, ""


# ---- comment / uncomment ------------------------------------------------

def comment(ed, info):
    _dispatch(ed, info, commenting=True)


def uncomment(ed, info):
    _dispatch(ed, info, commenting=False)


def _in_outer_whitespace(ed, pos, line):
    line_start = ed.positionFromLine(line)
    line_end = ed.lineEndPosition(line)
    text = _text(ed, line_start, line_end)
    if not text.strip(" \t"):
        return True
    leading = _byte_len(text) - _byte_len(text.lstrip(" \t"))
    trailing_start = line_start + _byte_len(text.rstrip(" \t"))
    return line_start <= pos <= line_start + leading or trailing_start < pos <= line_end


def _dispatch(ed, info, commenting):
    line_worker = _comment_lines if commenting else _uncomment_lines
    block_worker = _comment_block if commenting else _uncomment_block
    sel_start = ed.selectionStart()
    sel_end = ed.selectionEnd()
    if not commenting and sel_end > sel_start:
        # If the selection is wrapped in a block delimiter pair, use it.
        for prefix, suffix in info.get("block", []):
            if _selection_delimiter_positions(ed, sel_start, sel_end, prefix, suffix):
                block_worker(ed, info, sel_start, sel_end)
                return
    start_line = ed.lineFromPosition(sel_start)
    end_line = ed.lineFromPosition(sel_end)
    # Block commenting is preferred when the selection starts or ends
    # within a line (ignoring leading/trailing whitespace).
    prefer_block = not (
        sel_start == sel_end
        or (_in_outer_whitespace(ed, sel_start, start_line)
            and _in_outer_whitespace(ed, sel_end, end_line))
    )
    if info.get("block") and (prefer_block or ("line" not in info and sel_start < sel_end)):
        block_worker(ed, info, sel_start, sel_end)
        return
    if not info.get("line"):
        if not info.get("block"):
            return
        # Block-only language with a line-wise selection: use the block
        # pair as line delimiters.
        info = dict(info, line=info["block"])
    text_start = ed.positionFromLine(start_line)
    if sel_start != sel_end and ed.column(sel_end) == 0:
        text_end = sel_end  # the line the selection ends at isn't included
    else:
        text_end = ed.lineEndPosition(end_line)
    line_worker(ed, info, text_start, text_end)


def _working_end(ed, sel_start, sel_end, end):
    if sel_start != sel_end and ed.column(sel_end) == 0:
        # At the start of a line: work from the end of the previous one.
        return ed.lineEndPosition(ed.lineFromPosition(end) - 1)
    return end


def _common_indent(lines):
    indent_re = re.compile(r"^(\s+).*$")
    non_blank = [text for text, _eol in lines if text.strip()]
    if not non_blank:
        return ""
    match = indent_re.search(non_blank[0])
    common = match.group(1) if match else ""
    for text in non_blank:
        match = indent_re.search(text)
        if not match:
            return ""
        while common and not match.group(1).startswith(common):
            common = common[:-1]
        if not common:
            return ""
    return common


def _apply_lines(ed, first_line, replacement_lines):
    """One line at a time, so markers (bookmarks, breakpoints) survive."""
    ed.beginUndoAction()
    try:
        for i, line in enumerate(replacement_lines):
            _replace(ed, ed.positionFromLine(first_line + i), ed.lineEndPosition(first_line + i),
                     line.rstrip("\r\n"))
    finally:
        ed.endUndoAction()


def _restore_line_selection(ed, sel_start, sel_end, start, end, working_end,
                            keep_if_within, shift):
    first_line = ed.lineFromPosition(start)
    last_line = ed.lineFromPosition(end)
    if sel_start != sel_end:
        new_end = ed.lineEndPosition(last_line) if end == working_end else ed.positionFromLine(last_line)
        ed.setSel(ed.positionFromLine(first_line), new_end)
    elif keep_if_within:
        ed.setSel(sel_start, sel_end)
    else:
        ed.setSel(sel_start + shift, sel_end + shift)


def _comment_lines(ed, info, start, end):
    x_offset = ed.xOffset()
    sel_start, sel_end = ed.selectionStart(), ed.selectionEnd()
    working_end = _working_end(ed, sel_start, sel_end, end)
    original = _text(ed, start, working_end)
    prefix, suffix = _delimiter_pair(info["line"][0])
    lines = _split_lines(original)
    indent = _common_indent(lines)
    replacement_lines = [indent + prefix + text[len(indent):] + suffix + eol for text, eol in lines]
    if "".join(replacement_lines) == original:
        return
    sel_start_column = ed.column(sel_start)
    _apply_lines(ed, ed.lineFromPosition(start), replacement_lines)
    _restore_line_selection(ed, sel_start, sel_end, start, end, working_end,
                            sel_start_column <= len(indent), _byte_len(prefix))
    ed.setXOffset(x_offset)


def _uncomment_lines(ed, info, start, end):
    x_offset = ed.xOffset()
    sel_start, sel_end = ed.selectionStart(), ed.selectionEnd()
    working_end = _working_end(ed, sel_start, sel_end, end)
    original = _text(ed, start, working_end)
    replacement_lines = []
    last_indent = last_prefix = ""
    for text, eol in _split_lines(original):
        for delimiter in info["line"]:
            prefix, suffix = _delimiter_pair(delimiter)
            if suffix:
                comment_re = r"^(\s*)(%s)(.*)(%s)(\s*)$" % (re.escape(prefix), re.escape(suffix))
            else:
                comment_re = r"^(\s*)(%s)(.*)()()$" % re.escape(prefix)
            match = re.search(comment_re, text)
            if match:
                replacement_lines.append(match.group(1) + match.group(3) + match.group(5) + eol)
                last_indent, last_prefix = match.group(1), match.group(2)
                break
        else:
            replacement_lines.append(text + eol)
    if "".join(replacement_lines) == original:
        return
    sel_start_column = ed.column(sel_start)
    _apply_lines(ed, ed.lineFromPosition(start), replacement_lines)
    _restore_line_selection(ed, sel_start, sel_end, start, end, working_end,
                            sel_start_column <= len(last_indent), -_byte_len(last_prefix))
    ed.setXOffset(x_offset)


def _comment_block(ed, info, start, end):
    prefix, suffix = info["block"][0]
    x_offset = ed.xOffset()
    sel_start, sel_end = ed.selectionStart(), ed.selectionEnd()
    # Insert rather than replace the whole range, so markers survive.
    ed.beginUndoAction()
    try:
        _replace(ed, end, end, suffix)
        _replace(ed, start, start, prefix)
    finally:
        ed.endUndoAction()
    ed.setSel(sel_start + _byte_len(prefix), sel_end + _byte_len(prefix))
    ed.setXOffset(x_offset)


def _selection_delimiter_positions(ed, start, end, prefix, suffix):
    """Handles /*|abc|*/  |/*abc*/|  |/*abc|*/  /*|abc*/| ('|' = selection)."""
    plen, slen = _byte_len(prefix), _byte_len(suffix)
    p_start = None
    if start >= plen and _text(ed, start - plen, start) == prefix:
        p_start, p_end = start - plen, start
    elif start + plen < end and _text(ed, start, start + plen) == prefix:
        p_start, p_end = start, start + plen
    if p_start is None:
        return None
    if end < ed.length() - slen and _text(ed, end, end + slen) == suffix:
        s_start, s_end = end, end + slen
    elif p_end <= end - slen and _text(ed, end - slen, end) == suffix:
        s_start, s_end = end - slen, end
    else:
        return None
    return p_start, p_end, s_start, s_end


def _uncomment_block(ed, info, start, end):
    for prefix, suffix in info["block"]:
        positions = _selection_delimiter_positions(ed, start, end, prefix, suffix)
        if positions is None:
            continue
        p_start, p_end, s_start, s_end = positions
        x_offset = ed.xOffset()
        ed.beginUndoAction()
        try:
            _replace(ed, s_start, s_end, "")  # suffix first, keeps p_* valid
            _replace(ed, p_start, p_end, "")
        finally:
            ed.endUndoAction()
        ed.setSel(p_start, s_start - _byte_len(prefix))
        ed.setXOffset(x_offset)
        return


# ---- text conversion ----------------------------------------------------

def title_case(text):
    return "".join(m.group(1) + m.group(2)[0].upper() + m.group(2)[1:]
                   for m in re.finditer(r"(\s*)(\S+)", text))


def to_hex(text):
    return text.encode("utf-8").hex()


def from_hex(text):
    return bytes.fromhex(text).decode("utf-8")


def convert_selection_by_line(ed, converter):
    """_do_cmd_convertCaseByLine: one line at a time keeps markers and
    lets str methods handle non-ASCII case mapping."""
    sel_start, sel_end = ed.selectionStart(), ed.selectionEnd()
    ed.beginUndoAction()
    try:
        for line in range(ed.lineFromPosition(sel_start), ed.lineFromPosition(sel_end) + 1):
            line_start = ed.getLineSelStartPosition(line)
            line_end = min(ed.lineEndPosition(line), ed.getLineSelEndPosition(line))
            if line_start < 0:
                continue
            text = _text(ed, line_start, line_end)
            fixed = converter(text)
            _replace(ed, line_start, line_end, fixed)
            sel_end += _byte_len(fixed) - _byte_len(text)
    finally:
        ed.endUndoAction()
    ed.setSel(sel_start, sel_end)


def _classify_ws(text, tab_width):
    """(raw leading whitespace chars, effective column width)."""
    raw = effective = 0
    for ch in text:
        if ch == " ":
            effective += 1
        elif ch == "\t":
            effective = (effective // tab_width + 1) * tab_width
        else:
            break
        raw += 1
    return raw, effective


def _tabify_line(text, tab_width):
    raw, effective = _classify_ws(text, tab_width)
    tabs, spaces = divmod(effective, tab_width)
    return "\t" * tabs + " " * spaces + text[raw:]


def _untabify_line(text, tab_width):
    return text.expandtabs(tab_width)


def tabify(ed, tab_width):
    _tabify_region(ed, tab_width, _tabify_line)


def untabify(ed, tab_width):
    _tabify_region(ed, tab_width, _untabify_line)


def _tabify_region(ed, tab_width, repl):
    """No selection: whole buffer (Komodo 7+). Tabify only touches leading
    whitespace, untabify every tab on the line."""
    if ed.length() == 0:
        return
    caret_line = ed.lineFromPosition(ed.currentPos())
    caret_column = ed.column(ed.currentPos())
    if ed.selectionStart() == ed.selectionEnd():
        lines = range(ed.lineCount())
        bounds = lambda n: (ed.positionFromLine(n), ed.lineEndPosition(n))  # noqa: E731
    else:
        lines = range(ed.lineFromPosition(ed.selectionStart()),
                      ed.lineFromPosition(ed.selectionEnd()) + 1)
        bounds = lambda n: (ed.getLineSelStartPosition(n), ed.getLineSelEndPosition(n))  # noqa: E731
    ed.beginUndoAction()
    try:
        for line in lines:
            start, end = bounds(line)
            if start < 0 or start == end:
                continue
            text = _text(ed, start, end)
            new = repl(text, tab_width)
            if new != text:
                _replace(ed, start, end, new)
    finally:
        ed.endUndoAction()
    ed.gotoPos(ed.findColumn(caret_line, caret_column))


def join_lines(ed):
    """_do_cmd_join: join the caret line with the next, one space between."""
    ed.beginUndoAction()
    try:
        line = ed.lineFromPosition(ed.currentPos())
        line_end = ed.lineEndPosition(line)
        if _text(ed, ed.currentPos(), line_end).strip():
            ed.lineEnd()  # mid-line: act as if at the end of it
        whitespace_to_left = ed.charAt(ed.currentPos() - 1) == ord(" ")
        ed.lineEnd()
        start = end = ed.currentPos()
        buffer_end = ed.textLength()
        line_start = ed.positionFromLine(ed.lineFromPosition(start))
        if _text(ed, line_start, start).strip():
            while start >= line_start + 1 and ed.charAt(start - 1) == ord(" "):
                start -= 1
            replacement = " "
        else:
            replacement = ""
        while end < buffer_end and chr(ed.charAt(end) & 0xFF) in " \r\n":
            end += 1
        _replace(ed, start, end, replacement)
        ed.gotoPos(ed.targetEnd() if whitespace_to_left else ed.targetStart())
    finally:
        ed.endUndoAction()


def remove_trailing_whitespace(ed):
    """Selection only if there is one, else the whole document."""
    selection = ed.selectionStart() != ed.selectionEnd()
    if selection:
        start_line = ed.lineFromPosition(ed.selectionStart())
        start_column = ed.column(ed.selectionStart())
        end_line = ed.lineFromPosition(ed.selectionEnd())
        end_column = ed.column(ed.selectionEnd())
    else:
        start_line, end_line = 0, ed.lineCount() - 1
    ed.beginUndoAction()
    try:
        for line in range(start_line, end_line + 1):
            start, end = ed.positionFromLine(line), ed.lineEndPosition(line)
            text = _text(ed, start, end)
            if text != text.rstrip():
                _replace(ed, start, end, text.rstrip())
    finally:
        ed.endUndoAction()
    if selection:
        ed.setSel(ed.findColumn(start_line, start_column), ed.findColumn(end_line, end_column))


def clean_line_endings(ed):
    """koDocument.cleanLineEndings: every EOL to the document's mode."""
    ed.convertEOLs(ed.eOLMode())


# ---- navigation ---------------------------------------------------------

def move_current_line_to_top(ed):
    first_visible = ed.firstVisibleLine()
    current = ed.visibleFromDocLine(ed.lineFromPosition(ed.currentPos()))
    ed.lineScroll(0, current - first_visible)


def _is_header(ed, line):
    return ed.foldLevel(line) & FOLDLEVELHEADERFLAG


def _level(ed, line):
    return ed.foldLevel(line) & FOLDLEVELNUMBERMASK


def _closest_fold_line(ed, line, ancestor=0):
    """Closest header line (preferring up) at `line`'s fold level, going
    `ancestor` levels up the hierarchy when there is none."""
    initial = line
    level = _level(ed, line) - ancestor
    if level <= FOLDLEVELBASE:
        return None
    while not _is_header(ed, line) or _level(ed, line) != level:
        if line == 0 or _level(ed, line) < level:
            line = initial
            while not _is_header(ed, line) or _level(ed, line) != level:
                if line >= ed.lineCount() or _level(ed, line) < level:
                    return _closest_fold_line(ed, initial, ancestor + 1)
                line += 1
            return line
        line -= 1
    return line


def _jump_to_sibling_fold(ed, delta, end_line):
    line = ed.lineFromPosition(ed.currentPos())
    if line == end_line:
        return
    closest = _closest_fold_line(ed, line)
    if closest is None:
        ed.gotoLine(end_line)
        return
    desired = _level(ed, closest)
    line += delta
    while not _is_header(ed, line) or _level(ed, line) > desired:
        if line == end_line:
            return
        line += delta
    if _level(ed, line) == desired:
        ed.gotoLine(line)


def jump_to_previous_fold(ed):
    _jump_to_sibling_fold(ed, -1, 0)


def jump_to_next_fold(ed):
    _jump_to_sibling_fold(ed, 1, ed.lineCount())


def jump_to_parent_fold(ed):
    line = ed.lineFromPosition(ed.currentPos())
    level = _level(ed, line)
    if level <= FOLDLEVELBASE:
        return
    while not _is_header(ed, line) or _level(ed, line) > level - 1:
        if line == 0:
            return
        line -= 1
    ed.gotoLine(line)


# ---- bookmarks ----------------------------------------------------------

def setup_bookmark_marker(ed, margin):
    """markers.js defines bookmark.xpm as a pixmap marker. The PySide
    bindings of markerDefinePixmap/markerDefineRGBAImage are broken
    (NameError at call time), so Qt decodes the XPM and the RGBA bytes go
    through send(); Scintilla copies them immediately."""
    image = QImage(BOOKMARK_XPM_PATH).convertToFormat(QImage.Format.Format_RGBA8888)
    pixels = ctypes.create_string_buffer(bytes(image.constBits()), image.sizeInBytes())
    ed.rGBAImageSetWidth(image.width())
    ed.rGBAImageSetHeight(image.height())
    ed.send(int(Scintilla.Message.MarkerDefineRGBAImage), MARKNUM_BOOKMARK, ctypes.addressof(pixels))
    ed.setMarginMaskN(margin, ed.marginMaskN(margin) | (1 << MARKNUM_BOOKMARK))


def toggle_bookmark(ed):
    line = ed.lineFromPosition(ed.currentPos())
    if ed.markerGet(line) & (1 << MARKNUM_BOOKMARK):
        ed.markerDelete(line, MARKNUM_BOOKMARK)
    else:
        ed.markerAdd(line, MARKNUM_BOOKMARK)


def remove_all_bookmarks(ed):
    ed.markerDeleteAll(MARKNUM_BOOKMARK)


def goto_next_bookmark(ed):
    """Returns False (Komodo: 'No next bookmark can be found') if there is
    no other bookmarked line."""
    this_line = ed.lineFromPosition(ed.selectionStart())
    mask = 1 << MARKNUM_BOOKMARK
    line = ed.markerNext(this_line + 1, mask)
    if line < 0:
        line = ed.markerNext(0, mask)
    return _goto_bookmark(ed, line, this_line)


def goto_previous_bookmark(ed):
    this_line = ed.lineFromPosition(ed.selectionStart())
    mask = 1 << MARKNUM_BOOKMARK
    line = ed.markerPrevious(this_line - 1, mask)
    if line < 0:
        line = ed.markerPrevious(ed.lineCount() - 1, mask)
    return _goto_bookmark(ed, line, this_line)


def _goto_bookmark(ed, line, this_line):
    if line < 0 or line == this_line:
        return False
    ed.ensureVisibleEnforcePolicy(line)
    ed.gotoLine(line)
    return True
