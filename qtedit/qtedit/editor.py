"""Scintilla-based code editor widget with Pygments-driven container
highlighting.

pyside6-scintilla exposes Scintilla's raw SCI_* message API but no Lexilla
lexer factory, so there is no "built-in" per-language highlighting to turn
on. We do our own container-style highlighting instead: re-tokenize the
buffer with Pygments after real edits and paint styles ourselves via
startStyling/setStyling. This re-lexes the whole document on every edit,
which is fine for MVP-sized files but not incremental -- a known limitation
to revisit once this grows beyond a spike.
"""
import os
import re

from PySide6.QtCore import Signal
from PySide6.QtGui import QFontDatabase
from pygments.lexers import get_lexer_for_filename, get_lexer_by_name
from pygments.util import ClassNotFound
from pygments.token import Token
from pyside6_scintilla import ScintillaEdit, Scintilla

from qtedit import editor_commands
from qtedit.prefs import get_global_prefs
from qtedit.udl import styles as udl_styles
from qtedit.udl.interpreter import FOLD_LEVEL_BASE, UDLInterpreter
from qtedit.udl.lexres import LexResParseError, find_lexres_for_language, parse_lexres

# File extensions that should try a UDL language definition before falling
# back to Pygments -- see qtedit/qtedit/udl/. Only languages with a
# prebuilt .lexres under build/release/udl/build/ actually take effect (see
# find_lexres_for_language); everything else silently falls through to
# Pygments regardless of what's listed here.
UDL_EXTENSIONS = {
    ".r": "R",
    ".rst": "reStructuredText",
    ".html": "HTML",
    ".htm": "HTML",
    ".xml": "XML",
    # The remaining UDL languages with a prebuilt .lexres -- extensions
    # below are each that language's own well-established, unambiguous
    # convention (verified where possible against
    # src/python-sitelib/langinfo_prog.py; the rest are standard
    # industry conventions for these template engines, e.g. Twig->.twig).
    # A handful of UDL languages (Django, AngularJS, TracWiki, JSERB,
    # Komodo_Snippet) have no safe unambiguous extension of their own
    # (Django/AngularJS templates are typically plain .html, chosen by
    # explicit language selection in real Komodo too) -- those are still
    # reachable via the Edit > Set Language... picker below, just not
    # auto-detected.
    ".as": "ActionScript",
    ".asc": "ActionScript",
    ".jsx": "JSX",
    ".php": "PHP",
    ".tpl": "Smarty",
    ".haml": "Haml",
    ".hbs": "Handlebars",
    ".handlebars": "Handlebars",
    ".mustache": "Mustache",
    ".twig": "Twig",
    ".j2": "Jinja2",
    ".jinja2": "Jinja2",
    ".jinja": "Jinja2",
    ".tt": "TemplateToolkit",
    ".tt2": "TemplateToolkit",
    ".mas": "Mason",
    ".mc": "Mason",
    ".mi": "Mason",
    ".rhtml": "RHTML",
    ".erb": "RHTML",
    ".xbl": "XBL",
    ".xul": "XUL",
    ".mxml": "MXML",
    ".ejs": "EJS",
    ".ep": "epMojo",
    ".xsl": "XSLT",
    ".xslt": "XSLT",
    # Fittingly self-referential: .udl source files are themselves written
    # in the Luddite language that luddite/lexres.py's compiler consumes.
    ".udl": "Luddite",
}

# Files matched by exact (lowercased) basename rather than extension --
# Dockerfiles conventionally have no extension at all, so UDL_EXTENSIONS'
# os.path.splitext lookup can never match them.
UDL_FILENAMES = {
    "dockerfile": "Docker",
}

# Files matched by a (lowercased) basename *suffix* -- Laravel Blade's
# convention is a compound "name.blade.php" extension, so a plain
# os.path.splitext (which only ever sees ".php") can't distinguish it from
# regular PHP. Checked before UDL_EXTENSIONS so it takes priority over the
# plain ".php" -> PHP mapping above.
UDL_FILENAME_SUFFIXES = {
    ".blade.php": "LaravelBlade",
}

# All UDL languages with a prebuilt .lexres, in a stable display order --
# used by the Edit > Set Language... picker (main_window.py) so every
# language is manually reachable even without an extension mapping above.
UDL_LANGUAGES = sorted(
    {
        "R", "reStructuredText", "HTML", "XML", "Docker", "ActionScript",
        "AngularJS", "Django", "EJS", "epMojo", "Haml", "Handlebars",
        "Jinja2", "JSERB", "JSX", "Komodo_Snippet", "LaravelBlade",
        "Luddite", "Mason", "Mustache", "MXML", "PHP", "RHTML", "Smarty",
        "TemplateToolkit", "TracWiki", "Twig", "XBL", "XSLT", "XUL",
    }
)

SC_CP_UTF8 = 65001
STYLE_DEFAULT = 32

# Scintilla has no theme concept of its own -- every colour is set
# explicitly per style, so unlike the rest of the (Qt-themed) UI, the editor
# surface stays whatever we hardcode here regardless of dark/light mode.
# Komodo's legacy Mozilla/XUL build did the same (its skins set editor
# colours directly). These values are Komodo's actual shipped default
# scheme (src/schemes/color_schemes/Default.ksf), not an invented palette --
# converted from that file's decimal BGR integers (Scintilla's native
# colour order) to the 0xBBGGRR hex this module already uses.
BACKGROUND = 0x332C2C  # default_fixed.back
FOREGROUND = 0xFFFFFF  # identifiers / default_fixed.fore
# Margin numbers follow Komodo's own layout (SciMoz/ISciMoz.template.idl):
# 0 symbols (breakpoints, bookmarks), 1 line numbers, 3 folding.
BREAKPOINT_MARGIN = 0
LINE_NUMBER_MARGIN = 1
MARKER_BREAKPOINT = 1
MARKER_CURRENT_LINE = 2
MARKER_BREAKPOINT_COND = 3  # has a condition and/or ignore count set
BREAKPOINT_COLOR = 0x2020E0  # a clear, conventional breakpoint red
BREAKPOINT_COND_COLOR = 0x20A0E0  # orange -- visually distinct from a plain breakpoint
CURRENT_LINE_COLOR = 0x30B8E0  # amber execution-line highlight
FOLD_MARGIN = 3
# koDocumentSettingsManager._apply_editFoldStyle: 15px, and only for
# languages that can fold at all (here: UDL-lexed buffers).
FOLD_MARGIN_WIDTH = 15
FOLD_MARGIN_COLOR = 0x332C2C  # Colors.foldMarginColor
LINE_NUMBER_FONT_SIZE = 10  # linenumbers.size
LINE_SPACING = 2  # default_fixed.lineSpacing, split into extra ascent/descent

# default_fixed.face/size from the same Default.ksf: a CSS-style fallback
# list, resolved to the first family actually installed (see _editor_font).
EDITOR_FONT_FACES = [
    "Monaco", "Consolas", "Inconsolata", "DejaVu Sans Mono",
    "Bitstream Vera Sans Mono", "Menlo", "Courier New", "Courier", "Monospace",
]
EDITOR_FONT_SIZE = 11

MARGIN_BACKGROUND = 0x242020  # linenumbers.back == Colors.caretLineBack
MARGIN_FOREGROUND = 0x969896  # linenumbers.fore
SELECTION_BACKGROUND = 0x4C4444  # Colors.selBack
CARET_COLOR = 0xFFFFFF

# (Pygments token, Scintilla style id, foreground 0xBBGGRR)
# Komodo's Default.ksf doesn't set `bold` on any of these (only on
# default_fixed, which is off) -- unlike the invented palette this replaced,
# nothing here is bold.
TOKEN_STYLES = [
    (Token.Comment, 1, 0x776E65),  # comments
    (Token.String, 2, 0x63E8C6),  # strings
    (Token.Number, 3, 0x5EC4DB),  # numbers
    (Token.Keyword, 4, 0x2EACDD),  # keywords
    (Token.Name.Function, 5, 0xBEA281),  # functions
    # Komodo's scheme has no dedicated class colour; keywords2 (its
    # secondary-keyword colour) is the closest semantic match.
    (Token.Name.Class, 6, 0x446AFF),  # keywords2
    (Token.Operator, 7, 0xFF8A3F),  # operators
    (Token.Name.Builtin, 8, 0xBEA281),  # functions
]


# Scintilla's batch lexer (SCLEX_BATCH, LexBatch.cxx) as Komodo drives it:
# koBATLanguage sets no keyword list, so only comments (REM, ::), labels,
# drive changes (styled SCE_BAT_WORD) and operators stand out; commands,
# %variables% and the "@" hide marker map to scheme styles Default.ksf
# leaves at the default colour (src/schemes/styles.py 'Batch').
BATCH_COMMENT_STYLE = 1  # comments
BATCH_WORD_STYLE = 4  # keywords
BATCH_LABEL_STYLE = 5  # functions
BATCH_OPERATOR_STYLE = 7  # operators
_BATCH_OPERATORS = set("=+><|?*&()")  # IsBOperator
_BATCH_DRIVE_CHANGE = re.compile(r"[A-Za-z]:(?:\\)?(?=\s|$)")


def batch_pieces(text):
    """(text, style id) pieces for a batch file, line by line."""
    for line in text.splitlines(True):
        body = line.rstrip("\r\n")
        eol = line[len(body):]
        indent = len(body) - len(body.lstrip(" \t"))
        rest = body[indent:]
        yield body[:indent], STYLE_DEFAULT
        if rest.startswith("::"):
            yield rest, BATCH_COMMENT_STYLE
        elif rest.startswith(":"):
            yield rest, BATCH_LABEL_STYLE
        elif _BATCH_DRIVE_CHANGE.match(rest):
            yield rest, BATCH_WORD_STYLE
        else:
            if rest.startswith("@"):
                yield "@", STYLE_DEFAULT  # SCE_BAT_HIDE
                rest = rest[1:]
            word = rest.lstrip(" \t")
            if word[:3].lower() == "rem" and (len(word) == 3 or word[3] in " \t"):
                yield rest, BATCH_COMMENT_STYLE
            else:
                for ch in rest:
                    yield ch, BATCH_OPERATOR_STYLE if ch in _BATCH_OPERATORS else STYLE_DEFAULT
        yield eol, STYLE_DEFAULT


def _style_id_for(token_type):
    for token, style_id, _color in TOKEN_STYLES:
        if token_type in token:
            return style_id
    return STYLE_DEFAULT


def _udl_language_for_filename(filename):
    lower_basename = os.path.basename(filename).lower()
    udl_language = UDL_FILENAMES.get(lower_basename)
    if udl_language is None:
        for suffix, language in UDL_FILENAME_SUFFIXES.items():
            if lower_basename.endswith(suffix):
                return language
        udl_language = UDL_EXTENSIONS.get(os.path.splitext(lower_basename)[1])
    return udl_language


def language_for_filename(filename):
    """Display name of the language a file would open in, from its name
    only (no content sniffing): for icons in Recent Files and the like."""
    udl_language = _udl_language_for_filename(filename)
    if udl_language and find_lexres_for_language(udl_language):
        return udl_language
    try:
        lexer = get_lexer_for_filename(filename)
    except ClassNotFound:
        return None
    return editor_commands.komodo_language_name([lexer.name, *lexer.aliases]) or lexer.name


def _editor_font():
    installed = set(QFontDatabase.families())
    for face in EDITOR_FONT_FACES:
        if face in installed:
            return face
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()


class CodeEditor(ScintillaEdit):
    breakpointsChanged = Signal()  # emitted after a real user edit to
    # breakpoints/conditions/ignore counts -- NOT emitted by
    # restore_breakpoints(), so main_window.py's persistence hook doesn't
    # immediately re-save the same data it just loaded on file open.

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lexer = None
        self._udl_interpreter = None
        self._udl_language = None
        self._rehighlighting = False
        # Plain attribute, not a Qt property: ScintillaEdit already has an
        # (unrelated, read-only) meta-property literally named "filepath",
        # which silently swallows writes via setProperty("filepath", ...).
        self.filepath = None
        # Set instead of `filepath` when this tab is editing a toolbox
        # snippet's content (see main_window._open_snippet_editor) --
        # mirrors legacy Komodo opening snippets via a virtual `snippet2://`
        # URL in the main editor rather than a small dialog. Saving writes
        # back to the toolbox item's .komodotool file, not a real path.
        self.toolbox_item = None

        # Bumped on every real text change (see _on_modified below). Used
        # by main_window.py to detect and drop stale codeintel completion
        # responses -- the OOP round-trip is async and can take a few
        # seconds on a cold cache, so the buffer may well have changed by
        # the time a response arrives.
        self.edit_generation = 0

        self.setCodePage(SC_CP_UTF8)
        # styleClearAll() copies STYLE_DEFAULT's current attributes to every
        # style, so it must run *after* the default fore/back are set, not
        # before -- otherwise every style (including the token overrides
        # below) inherits Scintilla's built-in white background instead.
        self.styleSetFore(STYLE_DEFAULT, FOREGROUND)
        self.styleSetBack(STYLE_DEFAULT, BACKGROUND)
        self.styleSetFont(STYLE_DEFAULT, _editor_font())
        self.styleSetSize(STYLE_DEFAULT, EDITOR_FONT_SIZE)
        # Same split as koScintillaSchemeService: floor above, ceil below.
        self.setExtraAscent(LINE_SPACING // 2)
        self.setExtraDescent(LINE_SPACING - LINE_SPACING // 2)
        self.styleClearAll()
        for _token, style_id, color in TOKEN_STYLES:
            self.styleSetFore(style_id, color)

        self.styleSetFore(Scintilla.StylesCommon.LineNumber, MARGIN_FOREGROUND)
        self.styleSetBack(Scintilla.StylesCommon.LineNumber, MARGIN_BACKGROUND)
        self.styleSetSize(Scintilla.StylesCommon.LineNumber, LINE_NUMBER_FONT_SIZE)
        self.setCaretFore(CARET_COLOR)
        self.setCaretLineVisible(True)
        self.setCaretLineBack(MARGIN_BACKGROUND)
        self.setSelBack(True, SELECTION_BACKGROUND)

        self.setMarginTypeN(LINE_NUMBER_MARGIN, Scintilla.MarginType.Number)
        self.setMarginMaskN(LINE_NUMBER_MARGIN, 0)
        self._line_count = 0
        self._line_numbers_visible = True
        self._update_line_number_margin()

        # Margin 0: clickable breakpoint gutter (see debugger/ -- there is
        # no legacy breakpoint UI to match, this is a from-scratch design).
        self.setMarginTypeN(BREAKPOINT_MARGIN, Scintilla.MarginType.Symbol)
        self.setMarginWidthN(BREAKPOINT_MARGIN, 16)
        self.setMarginSensitiveN(BREAKPOINT_MARGIN, True)
        self.setMarginMaskN(
            BREAKPOINT_MARGIN, (1 << MARKER_BREAKPOINT) | (1 << MARKER_BREAKPOINT_COND)
        )
        self.markerDefine(Scintilla.MarkerSymbol.Circle, MARKER_BREAKPOINT)
        self.markerSetBack(MARKER_BREAKPOINT, BREAKPOINT_COLOR)
        self.markerSetFore(MARKER_BREAKPOINT, FOREGROUND)
        self.markerDefine(Scintilla.MarkerSymbol.Circle, MARKER_BREAKPOINT_COND)
        self.markerSetBack(MARKER_BREAKPOINT_COND, BREAKPOINT_COND_COLOR)
        self.markerSetFore(MARKER_BREAKPOINT_COND, FOREGROUND)
        # Komodo's bookmark pixmap shares the symbol margin.
        editor_commands.setup_bookmark_marker(self, BREAKPOINT_MARGIN)

        # Current-execution-line highlight: a full-line background marker,
        # not tied to any margin -- set/cleared by main_window.py while a
        # debug session is stopped.
        self.markerDefine(Scintilla.MarkerSymbol.Background, MARKER_CURRENT_LINE)
        self.markerSetBack(MARKER_CURRENT_LINE, CURRENT_LINE_COLOR)

        # Margin 3: folding gutter, driven by udl/interpreter.py's
        # compute_fold_levels() for UDL-lexed buffers (see _rehighlight
        # below) -- Pygments-lexed buffers just get an empty margin, since
        # Pygments has no fold-flipper data to draw from. Only the classic
        # two-marker +/- style is set up, not Scintilla's flattened-tree
        # connector markers (FolderSub/FolderTail/etc.) -- simpler and
        # sufficient for a first pass.
        self.setMarginTypeN(FOLD_MARGIN, Scintilla.MarginType.Symbol)
        self.setMarginWidthN(FOLD_MARGIN, 0)
        self.setMarginMaskN(FOLD_MARGIN, Scintilla.MaskFolders)
        self.setFoldMarginColour(True, FOLD_MARGIN_COLOR)
        self.setFoldMarginHiColour(True, FOLD_MARGIN_COLOR)
        self.markerDefine(Scintilla.MarkerSymbol.Plus, Scintilla.MarkerOutline.Folder)
        self.markerDefine(Scintilla.MarkerSymbol.Minus, Scintilla.MarkerOutline.FolderOpen)
        for marker in (Scintilla.MarkerOutline.Folder, Scintilla.MarkerOutline.FolderOpen):
            self.markerSetBack(marker, MARGIN_FOREGROUND)
            self.markerSetFore(marker, MARGIN_BACKGROUND)
        # Let Scintilla handle margin clicks/line show-hide itself instead
        # of routing SCN_MARGINCLICK through marginClicked (which this
        # class already uses for the breakpoint margin) -- no container-side
        # fold-toggle code needed.
        self.setAutomaticFold(
            Scintilla.AutomaticFold.Click
            | Scintilla.AutomaticFold.Show
            | Scintilla.AutomaticFold.Change
        )

        self.breakpoints = set()  # 0-based line numbers
        self.breakpoint_conditions = {}  # line -> condition expression string
        self.breakpoint_ignore_counts = {}  # line -> int, 0 means unset
        self.marginClicked.connect(self._on_margin_clicked)

        self.modified.connect(self._on_modified)

        self._prefs = get_global_prefs()
        self._apply_editor_prefs()
        self._prefs.changed.connect(self._on_pref_changed)

    def _apply_editor_prefs(self):
        self.setUseTabs(self._prefs.get("useTabs"))
        self.setTabWidth(self._prefs.get("tabWidth"))
        self.setIndent(self._prefs.get("indentWidth"))

    def _on_pref_changed(self, name):
        if name in ("useTabs", "tabWidth", "indentWidth"):
            self._apply_editor_prefs()

    def set_lexer_for_filename(self, filename, text=""):
        udl_language = _udl_language_for_filename(filename)
        if udl_language and self._set_udl_language(udl_language):
            return
        self._udl_interpreter = None
        try:
            self._lexer = get_lexer_for_filename(
                filename, text, stripnl=False, ensurenl=False
            )
        except ClassNotFound:
            self._lexer = None
        self._rehighlight()

    def set_lexer_by_name(self, name):
        if self._set_udl_language(name):
            return
        self._udl_interpreter = None
        try:
            self._lexer = get_lexer_by_name(name, stripnl=False, ensurenl=False)
        except ClassNotFound:
            self._lexer = None
        self._rehighlight()

    def _set_udl_language(self, language_name):
        """Try to lex with a real Komodo UDL language definition instead of
        Pygments. Returns whether one was actually found and loaded."""
        path = find_lexres_for_language(language_name)
        if not path:
            return False
        try:
            parsed = parse_lexres(path)
        except LexResParseError:
            return False
        self._udl_interpreter = UDLInterpreter(parsed)
        self._udl_language = language_name
        self._lexer = None
        self._rehighlight()
        return True

    def language_name(self):
        """Display name of the active language (statusbar language menu)."""
        if self._udl_interpreter is not None:
            return self._udl_language
        if self._lexer is not None:
            # Komodo's name for it ("Batch" for Pygments' "Batchfile").
            return editor_commands.komodo_language_name(
                [self._lexer.name, *self._lexer.aliases]) or self._lexer.name
        return None

    def language_names(self):
        """Candidate Komodo language names for this buffer: the display
        name, then the Pygments aliases ("Batchfile" is Komodo's "Batch")."""
        names = [self.language_name()]
        if self._udl_interpreter is None and self._lexer is not None:
            names.extend(self._lexer.aliases)
        return [n for n in names if n]

    def current_text(self):
        length = self.length()
        data = self.getText(length + 1)
        return bytes(data)[:length].decode("utf-8", errors="replace")

    def _on_modified(self, mod_type, *_rest):
        changed_text = mod_type & (
            Scintilla.ModificationFlags.InsertText
            | Scintilla.ModificationFlags.DeleteText
        )
        if changed_text:
            self.edit_generation += 1
            if self.lineCount() != self._line_count:
                self._update_line_number_margin()
        if changed_text and not self._rehighlighting:
            self._rehighlight()

    def set_line_numbers_visible(self, visible):
        """koDocumentSettingsManager._apply_showLineNumbers."""
        self._line_numbers_visible = visible
        if visible:
            self._update_line_number_margin()
        else:
            self.setMarginWidthN(LINE_NUMBER_MARGIN, 0)

    def _update_line_number_margin(self):
        """Port of SciMoz::UpdateMarginWidths: wide enough for the line
        count (at least two digits) plus 4px padding."""
        self._line_count = self.lineCount()
        if not self._line_numbers_visible:
            return
        digits = str(self._line_count) if self._line_count >= 100 else "00"
        width = self.textWidth(Scintilla.StylesCommon.LineNumber, digits) + 4
        self.setMarginWidthN(LINE_NUMBER_MARGIN, width)

    def _rehighlight(self):
        self.setMarginWidthN(
            FOLD_MARGIN, FOLD_MARGIN_WIDTH if self._udl_interpreter is not None else 0
        )
        if self._udl_interpreter is None and self._lexer is None:
            return
        self._rehighlighting = True
        try:
            text = self.current_text()
            data_len = len(text.encode("utf-8"))
            self.startStyling(0, 0)
            self.setStyling(data_len, STYLE_DEFAULT)
            if self._udl_interpreter is not None:
                # Materialized (not left as a generator) since it's also
                # needed below for fold-level computation.
                udl_spans = self._udl_interpreter.colorize(text)
                # UDLInterpreter.colorize() works in Python string (character)
                # offsets, so slice out each span's text rather than reusing
                # its offsets directly -- like the Pygments branch below, byte
                # length (not char count) is what startStyling/setStyling want.
                pieces = (
                    (text[start:end], udl_styles.scintilla_style_id(style_num))
                    for start, end, style_num in udl_spans
                )
            elif self.language_name() == "Batch":
                udl_spans = None
                pieces = batch_pieces(text)
            else:
                udl_spans = None
                pieces = (
                    (value, _style_id_for(token_type))
                    for token_type, value in self._lexer.get_tokens(text)
                )
            pos = 0
            for value, style_id in pieces:
                length = len(value.encode("utf-8"))
                if length:
                    self.startStyling(pos, 0)
                    self.setStyling(length, style_id)
                pos += length

            if udl_spans is not None:
                levels = self._udl_interpreter.compute_fold_levels(text, udl_spans)
            else:
                # Pygments-lexed buffers have no fold-flipper data to draw
                # from -- reset to a flat, headerless margin instead of
                # leaving stale fold markers from a previously UDL-lexed tab.
                levels = [FOLD_LEVEL_BASE] * (self.current_text().count("\n") + 1)
            for line, level in enumerate(levels):
                self.setFoldLevel(line, level)
        finally:
            self._rehighlighting = False

    def _on_margin_clicked(self, position, _modifiers, margin):
        if margin != BREAKPOINT_MARGIN:
            return
        self.toggle_breakpoint(self.lineFromPosition(position))

    def toggle_breakpoint(self, line):
        if line in self.breakpoints:
            self.breakpoints.discard(line)
            self.breakpoint_conditions.pop(line, None)
            self.breakpoint_ignore_counts.pop(line, None)
            self.markerDelete(line, MARKER_BREAKPOINT)
            self.markerDelete(line, MARKER_BREAKPOINT_COND)
        else:
            self.breakpoints.add(line)
            self.markerAdd(line, MARKER_BREAKPOINT)
        self.breakpointsChanged.emit()

    def set_breakpoint_condition(self, line, condition, ignore_count):
        """Attach a condition expression and/or ignore count to `line`,
        adding it as a plain breakpoint first if it isn't one already.
        Passing an empty condition and a zero ignore_count clears both and
        reverts the marker to the plain breakpoint look."""
        if line not in self.breakpoints:
            self.breakpoints.add(line)
        if condition:
            self.breakpoint_conditions[line] = condition
        else:
            self.breakpoint_conditions.pop(line, None)
        if ignore_count:
            self.breakpoint_ignore_counts[line] = ignore_count
        else:
            self.breakpoint_ignore_counts.pop(line, None)
        self.markerDelete(line, MARKER_BREAKPOINT)
        self.markerDelete(line, MARKER_BREAKPOINT_COND)
        marker = (
            MARKER_BREAKPOINT_COND
            if (line in self.breakpoint_conditions or line in self.breakpoint_ignore_counts)
            else MARKER_BREAKPOINT
        )
        self.markerAdd(line, marker)
        self.breakpointsChanged.emit()

    def restore_breakpoints(self, saved):
        """Set the editor's breakpoint state from persisted data (see
        debugger/breakpoint_store.py) -- deliberately does not emit
        breakpointsChanged, since this is initial state being loaded, not
        a user edit that needs to be re-persisted."""
        for bp in saved:
            line = bp["line"]
            self.breakpoints.add(line)
            condition = bp.get("condition")
            ignore_count = bp.get("ignore_count") or 0
            if condition:
                self.breakpoint_conditions[line] = condition
            if ignore_count:
                self.breakpoint_ignore_counts[line] = ignore_count
            marker = MARKER_BREAKPOINT_COND if (condition or ignore_count) else MARKER_BREAKPOINT
            self.markerAdd(line, marker)

    def set_current_line(self, line):
        self.markerDeleteAll(MARKER_CURRENT_LINE)
        self.markerAdd(line, MARKER_CURRENT_LINE)
        self.ensureVisible(line)
        self.scrollCaret()

    def clear_current_line(self):
        self.markerDeleteAll(MARKER_CURRENT_LINE)
