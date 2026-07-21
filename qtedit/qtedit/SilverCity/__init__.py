"""Pure-Python drop-in for the pieces of the SilverCity package that
qtedit's ported codeintel3 (Python-language slice) actually needs.

Not a general SilverCity reimplementation. Real SilverCity only exists in
this repo as a Python-2-compiled C extension (_SilverCity.so, built
against Python 2's C API) -- there's no PyPI package and no Python 3
build, so it simply cannot be imported under Python 3 (confirmed: its own
__init__.py does `import _SilverCity` at module load time, so even the
constants/wrapper modules are unusable without the compiled part). This
shim exists instead of attempting a C-level Python-3 port of
PySilverCity.cxx (which uses Python 2's C API directly, e.g. PyString_* --
a real C-porting project, not a Python fix) -- backed by Pygments instead,
which qtedit already depends on for editor syntax highlighting (see
qtedit/qtedit/editor.py). Only SCLEX_PYTHON is implemented; codeintel3's
copied file set has no other language's lang_*.py module registered
anyway, so nothing else is ever requested (see manager.py's dynamic
lang-module discovery, which only finds lang_python.py here).

ScintillaConstants.py itself is copied verbatim from the real SilverCity
source (src/silvercity/PySilverCity/SilverCity/ScintillaConstants.py) --
it's pure generated data (Scintilla style-id constants), no C dependency
at all, so no replacement was needed there.
"""
from .ScintillaConstants import *
from . import ScintillaConstants


class PropertySet:
    """Lexer-configuration property bag. Real SilverCity lexers read
    things like tab width from this; the Pygments-backed Python lexer
    doesn't need any of them, so this only exists to satisfy the
    PythonLexer(SilverCity.Lexer.Lexer).__init__ call shape."""

    def __init__(self):
        self._props = {}

    def set(self, name, value):
        self._props[name] = value

    def __getitem__(self, name):
        return self._props.get(name, "")


class WordList:
    """Real SilverCity.WordList also accepts a .lexres file path (for UDL
    lexers) -- not needed here since no UDL language is registered in
    this porting phase's copied file set."""

    def __init__(self, words):
        self.words = set(words.split()) if isinstance(words, str) else set(words)

    def __contains__(self, word):
        return word in self.words


def find_lexer_module_by_id(lexer_id):
    if lexer_id == ScintillaConstants.SCLEX_PYTHON:
        from .python_lexer import PygmentsPythonLexerModule
        return PygmentsPythonLexerModule()
    raise NotImplementedError(
        "SilverCity shim only implements SCLEX_PYTHON (lexer id %r requested) "
        "-- see the codeintel Python-3 port's scope in the plan doc" % (lexer_id,)
    )
