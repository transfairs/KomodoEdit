"""Komodo's paragraph reflow (src/python-sitelib/reflow.py), ported to
Python 3. Paragraph detection knows comment prefixes (#, //, /*, --, email
">"), bullets (*, -, %) and doctest-style code lines, and keeps their
indentation when rewrapping. The HTML conversion Komodo's module also has
is not used by the editor and was left out.

>>> reflow("This is a long paragraph which is useful in testing reflow\\n", 30, '\\n')
'This is a long paragraph which\\nis useful in testing reflow\\n'
>>> print(reflow("    > This is a really really really really really really really "
...              "really long sentence\\n    > and this is the next line.", 40, '\\n'))
    > This is a really really really
    > really really really really really
    > long sentence and this is the next
    > line.
>>> reflow("abcdefgh1 abcdefgh2 abcdefgh3\\xa0abcdefgh4\\xa0abcdefgh5 abcdefgh6", 35, '\\n')
'abcdefgh1 abcdefgh2\\nabcdefgh3\\xa0abcdefgh4\\xa0abcdefgh5\\nabcdefgh6'
"""
import re

TABWIDTH = 8


class Line(str):
    """A line that knows its indentation semantics: whitespace-only or
    not, its indent, whether it starts with a comment marker or a bullet,
    and the indent "after" the bullet.

    >>> t = Line("   * and so on")
    >>> t.bulleted, t.indentWidths, t.leadingIndent
    (True, [3, 5], '   ')
    >>> t = Line('   # foobar')
    >>> t.iscomment, t.uncomment()
    (True, 'foobar')
    >>> Line("#   on all platforms\\n").indentWidths
    [4]
    """

    def __init__(self, line):
        super().__init__()
        self._line = line
        self.iswhitespace = not line.strip()
        self.indentWidths = []
        self.iscode, self.codeIndent = findcode(line)
        self.isBlockComment = False
        self.iscomment, self.commentIndent = findcomment(line)
        if self.iscomment:
            self.bulleted, self.bullet = findbullet(line[len(self.commentIndent):])
            self.leadingIndent = self.commentIndent
        else:
            self.bulleted, self.bullet = findbullet(line)
            self.leadingIndent = line[:len(line) - len(line.lstrip())]
        self.leadingIndentWidth = len(self.leadingIndent)
        if self.bulleted:
            if self.iscomment:
                self.indentWidths = [self.leadingIndentWidth, len(self.commentIndent) + len(self.bullet)]
            else:
                self.indentWidths = [self.leadingIndentWidth, len(self.bullet)]
        else:
            self.indentWidths = [self.leadingIndentWidth]

    def uncomment(self):
        line = Line(self._line[len(self.commentIndent):])
        line.iscomment = self.iscomment
        line.leadingIndent = self.leadingIndent
        return line


bulletRe = re.compile(r"(\s*?[\*%-]\s+)(.*)")


def findbullet(line):
    """(bulleted, bullet incl. the whitespace after it) or (False, line).

    >>> findbullet("   * so")
    (True, '   * ')
    >>> findbullet('- - - ')
    (True, '- ')
    """
    match = bulletRe.match(line)
    return (True, match.group(1)) if match else (False, line)


# Email lines starting with ">", ">>" or "> >" but not Python's ">>>".
commentRe = re.compile(r"(\s*?(?:\/\*|(?:#+)|(?:>)|(?:>>)|(?:> >)|(?://+)|(?:--))(?!>)\s*)(.*)")


def findcomment(line):
    """(iscomment, indent through the whitespace after the marker).

    >>> findcomment('    ###  tomato')
    (True, '    ###  ')
    >>> findcomment('    >>>  tomato')
    (False, '    >>>  tomato')
    """
    match = commentRe.match(line)
    return (True, match.group(1)) if match else (False, line)


codeRe = re.compile(r"(\s*?)(?:>>>\s)|(?:\.\.\.\s)")


def findcode(line):
    """(iscode, indent) for doctest-style lines.

    >>> findcode("   >>> x = 3")
    (True, '   ')
    """
    match = codeRe.match(line)
    return (True, match.group(1)) if match else (False, line)


commentLineIndentRe = re.compile(r"(\s*?(?:\*)\s*)(.*)")


class BlockCommentLine(Line):
    """A line inside a /* ... */ block, where " * " counts as the comment
    indent."""

    def __init__(self, line):
        super().__init__(line)
        self.isBlockComment = True
        if not self.iscomment:
            self.indentWidths = []
            self.iscomment = True
            match = commentLineIndentRe.match(line)
            if match:
                self.commentIndent = match.group(1)
            self.bulleted, self.bullet = findbullet(line[len(self.commentIndent):])
            self.leadingIndent = self.commentIndent
            self.leadingIndentWidth = len(self.leadingIndent)
            if self.bulleted:
                self.indentWidths = [self.leadingIndentWidth, len(self.commentIndent) + len(self.bullet)]
            else:
                self.indentWidths = [self.leadingIndentWidth]


class Para(list):
    """
    >>> p = Para(Line("No indentation"))
    >>> p.accept(Line("   Indentation")), p.accept(Line("but no indent is ok"))
    (False, True)
    >>> b = Para(Line("  * this is a bullleted line"))
    >>> b.append(Line("    which accepts a line which is indented accordingly"))
    >>> b.append(Line("    and so on and so on and so on"))
    >>> b.reflow(30, '\\n')
    >>> list(b)
    ['  * this is a bullleted line\\n', '    which accepts a line which\\n', '    is indented accordingly\\n', '    and so on and so on and so\\n', '    on']
    """

    def __init__(self, line):
        super().__init__([line])
        self.iswhitespace = not line.strip()

    def accept(self, line):
        if line.iscode and self[0].iscode:
            return True  # code paragraphs take all code lines
        if line.bulleted or line.iswhitespace or self[-1].iswhitespace:
            return False  # these start a new paragraph
        return line.indentWidths[0] in self[0].indentWidths

    def reflow(self, width, eol):
        trail = self[-1][-1] if self[-1].endswith((" ", "\t")) else ""
        logical_line = Line(self[0].rstrip())
        for line in self[1:]:
            logical_line += " " + line.strip()
        newline = eol if self[-1].endswith(eol) else None
        first = self[0]
        if first.bulleted:
            prefix = first.leadingIndent if first.iscomment else ""
            first_indent = prefix + first.bullet
            other_indents = prefix + " " * len(first.bullet)
        else:
            first_indent = other_indents = first.leadingIndent
        # Komodo bug 83764: str.split() breaks at non-breaking spaces, so
        # split around them first and glue the pieces back on.
        words = []
        for part in logical_line[len(first_indent):].split("\xa0"):
            new_words = part.split()
            if words:
                words[-1] += "\xa0"
                if new_words:
                    words[-1] += new_words.pop(0)
            words += new_words
        if not words:
            return
        lines = []
        cur_line = first_indent + words[0]
        for word in words[1:]:
            if len(word) + len(cur_line) + 1 <= width:  # 1 for the space
                cur_line += " " + word
                continue
            lines.append(cur_line + eol)
            cur_line = other_indents + word
        if newline:
            cur_line += newline
        lines.append(cur_line + trail)
        self[:] = [Line(line) for line in lines]


class Paragraphize(list):
    """A whitespace-only line is its own paragraph and ends the one
    before; a bulleted line starts a new one.

    >>> Paragraphize("Foo\\nbar\\n\\nbaz")
    [['Foo\\n', 'bar\\n'], ['\\n'], ['baz']]
    """

    def __init__(self, text, isBlockComment=False):
        super().__init__()
        line_class = BlockCommentLine if isBlockComment else Line
        lines = [line_class(line) for line in text.expandtabs(TABWIDTH).splitlines(True)]
        if not lines:
            return
        current = Para(lines[0])
        self.append(current)
        for line in lines[1:]:
            if current.accept(line):
                if line.iscomment:
                    line = Line(line.uncomment())
                current.append(line)
            else:
                current = Para(line)
                self.append(current)


def reflow(text, width, eol, isBlockComment=False):
    paragraphs = Paragraphize(text, isBlockComment=isBlockComment)
    for para in paragraphs:
        para.reflow(width, eol)
    return "".join("".join(para) for para in paragraphs)
