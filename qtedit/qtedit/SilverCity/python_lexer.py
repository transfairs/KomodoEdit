"""Pygments-backed replacement for SilverCity's compiled Python lexer
module -- see this package's __init__.py docstring for why. Returned by
find_lexer_module_by_id(SCLEX_PYTHON), duck-type-compatible with what a
real SilverCity lexer module provides: a tokenize_by_style(buffer,
keyword_lists, properties[, call_back]) method (see Lexer.py).
"""
from pygments.lexers import PythonLexer as PygmentsPythonLexer
from pygments.token import Token

from .ScintillaConstants import (
    SCE_P_CLASSNAME,
    SCE_P_COMMENTLINE,
    SCE_P_DEFAULT,
    SCE_P_DEFNAME,
    SCE_P_IDENTIFIER,
    SCE_P_NUMBER,
    SCE_P_OPERATOR,
    SCE_P_STRING,
    SCE_P_TRIPLEDOUBLE,
    SCE_P_WORD,
)

# Checked in order, first match wins -- most-specific Pygments token types
# before their broader parents (e.g. Name.Class before Name).
_STYLE_FOR_TOKEN = [
    (Token.Keyword, SCE_P_WORD),
    (Token.Name.Class, SCE_P_CLASSNAME),
    (Token.Name.Function, SCE_P_DEFNAME),
    (Token.Literal.String.Doc, SCE_P_TRIPLEDOUBLE),
    (Token.Literal.String, SCE_P_STRING),
    (Token.Literal.Number, SCE_P_NUMBER),
    (Token.Comment, SCE_P_COMMENTLINE),
    (Token.Operator, SCE_P_OPERATOR),
    (Token.Punctuation, SCE_P_OPERATOR),
    (Token.Name, SCE_P_IDENTIFIER),
]


def _style_for(token_type):
    for prefix, style in _STYLE_FOR_TOKEN:
        if token_type in prefix:
            return style
    return SCE_P_DEFAULT


class PygmentsPythonLexerModule:
    def tokenize_by_style(self, buffer, keyword_lists, properties, call_back=None):
        # keyword_lists/properties are accepted for interface compatibility
        # with real SilverCity lexer modules but unused -- Pygments' own
        # Python lexer already knows Python's keywords, so the WordList
        # PythonLexer.__init__ builds from Keywords.python_keywords isn't
        # needed here.
        text = buffer.decode("utf-8", errors="replace") if isinstance(buffer, bytes) else buffer
        lexer = PygmentsPythonLexer(stripnl=False, ensurenl=False)
        tokens = []
        for index, token_type, value in lexer.get_tokens_unprocessed(text):
            if not value:
                continue
            # end_index is inclusive (see accessor.py's `token["end_index"] + 1`
            # usage when it needs an exclusive/slice-style end).
            token = {
                "start_index": index,
                "end_index": index + len(value) - 1,
                "style": _style_for(token_type),
                "text": value,
            }
            tokens.append(token)
            if call_back is not None:
                call_back(token)
        return tokens
