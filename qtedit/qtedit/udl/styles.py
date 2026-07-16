"""Maps Komodo's UDL style-number space to the small set of Scintilla style
ids editor.py already has colors for (see TOKEN_STYLES in editor.py).

The SCE_UDL_* constants (src/scintilla/include/SciLexer.h:1832-1886) are a
single, fixed enum shared by *every* UDL language regardless of which .udl
it came from -- each of the five families (Markup/CSS/CSL/SSL/Template) gets
its own numeric sub-range, but the meaning of each offset within a family
(default/comment/number/string/word/identifier/operator/...) is the same
across languages. That means this table, once built from the enum, works
for any future UDL language, not just the one it was written against.

Only the SSL (server-side language) family has actually been exercised so
far (R is the first UDL language wired in, via src/udl/udl/r-mainlex.udl);
the M/CSS/CSL/TPL entries are transcribed directly from the same enum but
untested against a real markup/template UDL language yet.
"""

# Semantic category -> editor.py Scintilla style id (see editor.py's
# TOKEN_STYLES and STYLE_DEFAULT). Categories without a close existing match
# fall back to a reasonable neighbor rather than inventing new colors.
CATEGORY_STYLE_ID = {
    "default": 32,  # STYLE_DEFAULT
    "comment": 1,
    "string": 2,
    "number": 3,
    "keyword": 4,
    "identifier": 32,  # no dedicated color yet; render as plain text
    "operator": 7,
    "variable": 8,
    "regex": 2,
    "tag": 6,
    "attribute": 5,
    "entity": 8,
}

# SCE_UDL_M_* (markup family, style numbers 0-14)
_MARKUP = {
    0: "default",
    1: "tag",  # STAGO: start-tag open, e.g. "<"
    2: "tag",  # TAGNAME
    3: "default",  # TAGSPACE
    4: "attribute",  # ATTRNAME
    5: "operator",  # OPERATOR, e.g. "=" in an attribute
    6: "tag",  # STAGC: start-tag close, ">"
    7: "tag",  # EMP_TAGC: empty-tag close, "/>"
    8: "string",  # attribute value
    9: "tag",  # ETAGO: end-tag open, "</"
    10: "tag",  # ETAGC: end-tag close
    11: "entity",
    12: "tag",  # PI: processing instruction
    13: "string",  # CDATA
    14: "comment",
}
# SCE_UDL_CSS_* (15-21)
_CSS = {
    15: "default",
    16: "comment",
    17: "number",
    18: "string",
    19: "keyword",
    20: "identifier",
    21: "operator",
}
# SCE_UDL_CSL_* (client-side language, e.g. embedded JS; 22-30)
_CSL = {
    22: "default",
    23: "comment",
    24: "comment",  # COMMENTBLOCK
    25: "number",
    26: "string",
    27: "keyword",
    28: "identifier",
    29: "operator",
    30: "regex",
}
# SCE_UDL_SSL_* (server-side language, e.g. R/PHP; 31-48) -- the only family
# actually exercised so far.
_SSL = {
    31: "default",
    40: "comment",
    41: "comment",  # COMMENTBLOCK
    42: "number",
    43: "string",
    44: "keyword",
    45: "identifier",
    46: "operator",
    47: "regex",
    48: "variable",
}
# SCE_UDL_TPL_* (template augmentation language, e.g. Smarty; 49-57)
_TPL = {
    49: "default",
    50: "comment",
    51: "comment",  # COMMENTBLOCK
    52: "number",
    53: "string",
    54: "keyword",
    55: "identifier",
    56: "operator",
    57: "variable",
}

STYLE_NUMBER_TO_CATEGORY = {}
for _table in (_MARKUP, _CSS, _CSL, _SSL, _TPL):
    STYLE_NUMBER_TO_CATEGORY.update(_table)


def scintilla_style_id(udl_style_number):
    category = STYLE_NUMBER_TO_CATEGORY.get(udl_style_number, "default")
    return CATEGORY_STYLE_ID.get(category, CATEGORY_STYLE_ID["default"])
