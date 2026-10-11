"""The inline emotion tag parser (doc 05 §5, OQ-AI-07 A; ai-ports "Inline emotion tag"; design D11).

The model is asked to begin its reply with `<e:label>`. The parser:
- buffers the head up to 32 characters, or until `>`, across chunk boundaries (leading whitespace is ignored);
- accepts only the 7 contract emotions: a valid tag yields `Emotion(label, "llm")`;
- otherwise (no tag, an invalid label, no `>` within 32 characters, or the stream ending first) yields the previous
  face with source `default`, and releases the buffered text (an invalid but complete tag is dropped, never released);
- strips stray tags (`<e:…>`) anywhere later, including a tag split across chunks, before tokens are yielded;
- drops the whitespace between the opening tag and the first visible text;
- (docs/ai/03 C6, ai-foundation design D16) given the speaker's name(s), drops a leading `<name>:` on the FIRST line,
  before or after the tag (case-insensitive, spaces allowed around the colon), holding at most the name's length + 2
  characters, so `Mei: <e:happy>Hi` keeps its emotion and `<e:happy>Mei: Hi` shows `Hi`. A name that only starts the
  same (`Meilin`) is released as text.

The same rules pass the shared fixtures in `backend/tests/fixtures/tag_parser/`, which a TS reference parser also runs.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

EMOTIONS = ("neutral", "happy", "sad", "angry", "surprised", "thinking", "embarrassed")
MAX_HEAD = 32
_TAG = re.compile(r"<e:[^<>]{0,30}>")
_PARTIAL = re.compile(r"<(?:e(?::[^<>]{0,30})?)?$")


@dataclass(frozen=True)
class ParsedEmotion:
    emotion: str
    source: str     # "llm" | "default"


@dataclass(frozen=True)
class ParsedText:
    text: str


Parsed = ParsedEmotion | ParsedText


def name_prefix(text: str, names: Sequence[str]) -> tuple[str, int]:
    """Whether `text` starts with `<name>:` ("match", chars to drop incl. trailing spaces), could still become one
    ("maybe", 0) or doesn't ("no", 0). Case-insensitive; spaces allowed around the colon."""
    t = text.lstrip()
    skipped = len(text) - len(t)
    low = t.casefold()
    maybe = False
    for name in sorted({n for n in names if n}, key=len, reverse=True):
        n = name.casefold()
        m = re.match(re.escape(n) + r"[ \t]*:[ \t]*", low)
        if m is not None:
            if m.end() == len(low):
                maybe = True   # "Mei: " so far: more spaces may follow, wait for real text
                continue
            return "match", skipped + m.end()
        if n.startswith(low) or (low.startswith(n) and not low[len(n):].strip(" \t")):
            maybe = maybe or len(low) <= len(n) + 2
    return ("maybe", 0) if maybe else ("no", 0)


class TagParser:
    def __init__(self, previous: str = "neutral", speaker: str | Sequence[str] | None = None) -> None:
        self.previous = previous if previous in EMOTIONS else "neutral"
        self.head = ""
        self.decided = False
        self.carry = ""
        self.lead = False   # after a complete opening tag: whitespace is dropped until the first visible text
        names = [speaker] if isinstance(speaker, str) else list(speaker or [])
        self.names = [n for n in names if n]
        self.name_done = not self.names   # the first-line name check has concluded
        self.nbuf = ""                    # visible text held while it could still be "<name>:"

    def _decide(self, emotion: str | None) -> list[Parsed]:
        self.decided = True
        return [ParsedEmotion(emotion, "llm") if emotion else ParsedEmotion(self.previous, "default")]

    def _name_before_tag(self) -> bool:
        """Before the tag is decided: drop a leading `<name>:` from the head. False while it could still be one."""
        if self.name_done:
            return True
        s = self.head.lstrip()
        if not s:
            return False
        if s.startswith("<"):
            return True   # a tag first: the name check runs after it, on the visible text
        state, drop = name_prefix(self.head, self.names)
        if state == "maybe":
            return False
        if state == "match":
            self.head = self.head[drop:]
        self.name_done = True
        return True

    def feed(self, chunk: str) -> list[Parsed]:
        if self.decided:
            return self._body(chunk)
        self.head += chunk
        if not self._name_before_tag():
            return []
        s = self.head.lstrip()
        if not s:
            return []
        if not ("<e:".startswith(s) or s.startswith("<e:")):
            return self._release_head(None, self.head)
        if s.startswith("<e:") and ">" in s:
            end = s.index(">")
            label = s[3:end]
            self.lead = True
            return self._release_head(label if label in EMOTIONS else None, s[end + 1:])
        if len(self.head) >= MAX_HEAD:
            return self._release_head(None, self.head)
        return []

    def _release_head(self, emotion: str | None, text: str) -> list[Parsed]:
        self.head = ""
        out = self._decide(emotion)
        out.extend(self._body(text))
        return out

    def _body(self, chunk: str) -> list[Parsed]:
        text = _TAG.sub("", self.carry + chunk)
        self.carry = ""
        if self.lead:
            text = text.lstrip()
            self.lead = not text
        m = _PARTIAL.search(text)
        if m is not None and len(text) - m.start() <= MAX_HEAD:
            self.carry = text[m.start():]
            text = text[:m.start()]
        if not self.name_done and text:
            self.nbuf += text
            state, drop = name_prefix(self.nbuf, self.names)
            if state == "maybe":
                return []
            text = self.nbuf[drop:].lstrip() if state == "match" else self.nbuf
            self.nbuf = ""
            self.name_done = True
        return [ParsedText(text)] if text else []

    def close(self) -> list[Parsed]:
        """The stream ended: an undecided head is released with the default face; a held partial tag is text."""
        out: list[Parsed] = []
        if not self.decided:
            head, self.head = self.head, ""
            out.extend(self._decide(None))
            text = _TAG.sub("", head)
        else:
            text = ""
        text = self.nbuf + text + self.carry   # a held "Mei" that never became "Mei:" is text
        self.nbuf = self.carry = ""
        if text:
            out.append(ParsedText(text))
        return out


def parse_all(chunks: list[str], previous: str = "neutral", speaker: str | None = None) -> tuple[ParsedEmotion, str]:
    """The fixture form: the emotion and the released text for a whole stream."""
    p = TagParser(previous, speaker)
    out: list[Parsed] = []
    for c in chunks:
        out.extend(p.feed(c))
    out.extend(p.close())
    emotions = [x for x in out if isinstance(x, ParsedEmotion)]
    assert len(emotions) == 1
    return emotions[0], "".join(x.text for x in out if isinstance(x, ParsedText))
