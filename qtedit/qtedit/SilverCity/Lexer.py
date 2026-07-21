"""Pure-Python base class -- copied verbatim from the real SilverCity
source (no C dependency in this file at all, `self._lexer` is whatever
find_lexer_module_by_id() returned, e.g. our Pygments-backed shim)."""


class Lexer:
    def tokenize_by_style(self, buffer, call_back=None):
        if call_back is not None:
            return self._lexer.tokenize_by_style(
                buffer, self._keyword_lists, self._properties, call_back
            )
        else:
            return self._lexer.tokenize_by_style(
                buffer, self._keyword_lists, self._properties
            )
