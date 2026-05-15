"""Optional Pygments-based syntax highlighting.

Falls back to no highlighting if Pygments is not installed.
"""
from __future__ import annotations

try:
    from pygments.lexers import get_lexer_for_filename
    from pygments.token import Keyword, String, Comment, Number, Name, Literal
    from pygments.util import ClassNotFound
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

KEYWORD = 'keyword'
STRING  = 'string'
COMMENT = 'comment'
NUMBER  = 'number'
BUILTIN = 'builtin'


def _categorize(ttype) -> str | None:
    if ttype in Keyword:
        return KEYWORD
    if ttype in String or ttype in Literal.String:
        return STRING
    if ttype in Comment:
        return COMMENT
    if ttype in Number or ttype in Literal.Number:
        return NUMBER
    if ttype in Name.Builtin:
        return BUILTIN
    return None


def get_lexer(filename: str):
    """Return a Pygments lexer for filename, or None if unavailable/unsupported."""
    if not _AVAILABLE or not filename:
        return None
    try:
        return get_lexer_for_filename(filename, stripall=False, ensurenl=False)
    except ClassNotFound:
        return None


def get_lexer_by_alias(alias: str):
    """Return a Pygments lexer by alias name, or None if not found.

    Raises ClassNotFound (re-exported) so the caller can show a useful message.
    """
    if not _AVAILABLE:
        return None
    from pygments.lexers import get_lexer_by_name
    return get_lexer_by_name(alias)


# Re-export so callers don't need to import pygments directly
if _AVAILABLE:
    from pygments.util import ClassNotFound as LexerNotFound
else:
    class LexerNotFound(Exception):  # type: ignore
        pass


def build_spans(lines, lexer) -> list[list[tuple[int, int, str]]]:
    """Tokenize all lines and return per-line span lists.

    Each span is (start_col, end_col, category). Multiline tokens (block
    comments, multiline strings) are split across line entries correctly
    because the full file is tokenized in one pass.
    """
    if lexer is None:
        return [[] for _ in lines]

    code = '\n'.join(line.text for line in lines)
    result: list[list[tuple[int, int, str]]] = [[] for _ in lines]

    line_idx = 0
    col = 0
    for ttype, value in lexer.get_tokens(code):
        cat = _categorize(ttype)
        parts = value.split('\n')
        for i, part in enumerate(parts):
            if i > 0:
                line_idx += 1
                col = 0
            if part and cat is not None and line_idx < len(result):
                result[line_idx].append((col, col + len(part), cat))
            col += len(part)

    return result
