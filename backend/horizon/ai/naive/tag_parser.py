"""The inline emotion tag parser (doc 05 §5, OQ-AI-07 A; ai-ports "Inline emotion tag"; design D11).

The model is asked to begin its reply with `<e:label>`. The parser:
- buffers the head up to 32 characters, or until `>`, across chunk boundaries (leading whitespace is ignored);
- accepts only the 7 contract emotions: a valid tag yields `Emotion(label, "llm")`;
- otherwise (no tag, an invalid label, no `>` within 32 characters, or the stream ending first) yields the previous
  face with source `default`, and releases the buffered text (an invalid but complete tag is dropped, never released);
- strips stray tags (`<e:…>`) anywhere later, including a tag split across chunks, before tokens are yielded;
- drops the whitespace between the opening tag and the first visible text.

The same rules pass the shared fixtures in `backend/tests/fixtures/tag_parser/`, which a TS reference parser also runs.
"""

from __future__ import annotations

import re
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


class TagParser:
    def __init__(self, previous: str = "neutral") -> None:
        self.previous = previous if previous in EMOTIONS else "neutral"
        self.head = ""
        self.decided = False
        self.carry = ""
        self.lead = False   # after a complete opening tag: whitespace is dropped until the first visible text

    def _decide(self, emotion: str | None) -> list[Parsed]:
        self.decided = True
        return [ParsedEmotion(emotion, "llm") if emotion else ParsedEmotion(self.previous, "default")]

    def feed(self, chunk: str) -> list[Parsed]:
        if self.decided:
            return self._body(chunk)
        self.head += chunk
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
        text += self.carry
        self.carry = ""
        if text:
            out.append(ParsedText(text))
        return out


def parse_all(chunks: list[str], previous: str = "neutral") -> tuple[ParsedEmotion, str]:
    """The fixture form: the emotion and the released text for a whole stream."""
    p = TagParser(previous)
    out: list[Parsed] = []
    for c in chunks:
        out.extend(p.feed(c))
    out.extend(p.close())
    emotions = [x for x in out if isinstance(x, ParsedEmotion)]
    assert len(emotions) == 1
    return emotions[0], "".join(x.text for x in out if isinstance(x, ParsedText))
