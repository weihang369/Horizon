"""A free, local repair for JSON answers (docs/ai/03 C7, §5 check 2; llm-parameters "JSON calls repair locally, then
retry once"; ai-foundation design D19).

Group A A3: 19 of 20 JSON-mode drafts were valid; the failure, and its paid retry, wrote a nickname in unescaped
double quotes inside a string (`"name": "Loretta "Rhett" Kowalski"`). `repair_json_quotes` fixes exactly that class:
a linear scan that, inside a string, escapes any `"` that does not END the string, i.e. one not followed (after
spaces) by `,` `:` `}` `]` or the end of the text. It runs only after a parse or validation failure, and its output
must still validate, so a wrong guess falls through to the one paid retry instead of becoming a bad draft.
"""

from __future__ import annotations

_CLOSERS = frozenset(",:}]")


def _closes(text: str, i: int) -> bool:
    """Whether the quote at `i` can end a JSON string: the next non-space character is a closer, or nothing."""
    j = i + 1
    n = len(text)
    while j < n and text[j] in " \t\r\n":
        j += 1
    return j >= n or text[j] in _CLOSERS


def repair_json_quotes(text: str) -> str:
    """Escape stray double quotes inside JSON strings. Text that is already valid JSON is returned unchanged
    (every in-string quote of valid JSON is either escaped or ends the string)."""
    out: list[str] = []
    in_str = False
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if not in_str:
            out.append(c)
            if c == '"':
                in_str = True
        elif c == "\\" and i + 1 < n:
            out.append(text[i:i + 2])
            i += 2
            continue
        elif c == '"':
            if _closes(text, i):
                out.append(c)
                in_str = False
            else:
                out.append('\\"')
        else:
            out.append(c)
        i += 1
    return "".join(out)
