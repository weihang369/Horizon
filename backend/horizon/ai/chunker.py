"""The KnowledgeIndexer (doc 05 §2.2; knowledge-memory-storage design D6): one implementation for both profiles.

`para@1`, tokenizer `utf8/4` (`count_tokens`):
- **Children** (indexed and cited) are the MockClient's `paragraphs()`: blocks split on blank lines, whitespace
  collapsed; a paragraph over 1 200 characters is cut at a sentence end near 900. A heading line on its own is its own
  passage (the portable test pins `# Soups` / `Miso first.` / `Then tofu.`).
- **Sections** (parents, what the LLM reads) are runs of children under one heading path, closed near 1 500 tokens.
- **Pages** come from `<!-- page N -->` marker lines (Docling output); a marker always ends a paragraph.
- **Locators:** `p. N` for paged documents; else `§ {nearest heading}`; else `¶ {n}` (1-based).
- `char_start`/`char_end` index the Markdown given (`extracted.md`): the raw text between them, whitespace-collapsed,
  is the child's text (and the first piece of a cut paragraph starts where the paragraph does).

Chunk sizes are AI-stage tunables (doc 05 §6); changing them bumps `CHUNKER_VERSION`, which makes reindex re-chunk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from horizon.domain.pricing import count_tokens

CHUNKER_VERSION = "para@1"
TOKENIZER = "utf8/4"
SECTION_TOKENS = 1500
LONG = 1200
CUT_NEAR = 900
_PAGE = re.compile(r"^\s*<!--\s*page\s+(\d+)\s*-->\s*$", re.IGNORECASE)
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


@dataclass(frozen=True)
class Child:
    text: str
    locator: str
    heading: str | None
    char_start: int
    char_end: int
    page: int | None
    tokens: int


@dataclass
class Section:
    heading_path: str | None
    children: list[Child] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(c.text for c in self.children)

    @property
    def tokens(self) -> int:
        return count_tokens(self.text)

    @property
    def char_start(self) -> int:
        return self.children[0].char_start

    @property
    def char_end(self) -> int:
        return self.children[-1].char_end

    @property
    def page_start(self) -> int | None:
        pages = [c.page for c in self.children if c.page is not None]
        return min(pages) if pages else None

    @property
    def page_end(self) -> int | None:
        pages = [c.page for c in self.children if c.page is not None]
        return max(pages) if pages else None


@dataclass(frozen=True)
class Chunked:
    sections: list[Section]
    pages: int | None

    @property
    def children(self) -> list[Child]:
        return [c for s in self.sections for c in s.children]


def _collapse(raw: str, offset: int) -> tuple[str, list[int]]:
    """Whitespace-collapse `raw`, returning the text and, per output character, its index in the document."""
    out: list[str] = []
    pos: list[int] = []
    gap = False
    for i, ch in enumerate(raw):
        if ch.isspace():
            gap = bool(out)
            continue
        if gap:
            out.append(" ")
            pos.append(offset + i - 1)
            gap = False
        out.append(ch)
        pos.append(offset + i)
    return "".join(out), pos


def _pieces(text: str) -> list[tuple[int, int]]:
    """The mock's long-paragraph rule, as [start, end) spans of `text` (whitespace at the cuts trimmed)."""
    spans: list[tuple[int, int]] = []
    start = 0
    while len(text) - start > LONG:
        rest = text[start:]
        cut = rest.rfind(". ", 0, CUT_NEAR)
        at = cut + 1 if cut > 300 else CUT_NEAR
        end = start + at
        spans.append((start, end))
        start = end
        while start < len(text) and text[start] == " ":
            start += 1
    spans.append((start, len(text)))
    return [(a, b) for a, b in spans if b > a]


def _blocks(md: str) -> list[tuple[int, int, int | None]]:
    """Paragraph blocks as (start, end, page): runs of non-blank, non-marker lines."""
    blocks: list[tuple[int, int, int | None]] = []
    page: int | None = None
    start: int | None = None
    end = 0
    pos = 0
    for line in md.splitlines(keepends=True):
        stripped = line.strip()
        m = _PAGE.match(line)
        if not stripped or m:
            if start is not None:
                blocks.append((start, end, page))
                start = None
            if m:
                page = int(m.group(1))
        else:
            if start is None:
                start = pos
            end = pos + len(line.rstrip("\r\n"))
        pos += len(line)
    if start is not None:
        blocks.append((start, end, page))
    return blocks


def chunk(markdown: str, *, paged: bool = False) -> Chunked:
    md = markdown
    heads: list[tuple[int, str]] = []
    children: list[tuple[Child, str | None]] = []
    max_page: int | None = None
    n = 0
    for start, end, page in _blocks(md):
        raw = md[start:end]
        text, pos = _collapse(raw, start)
        if not text:
            continue
        if page is not None:
            max_page = page if max_page is None else max(max_page, page)
        h = _HEADING.match(text) if "\n" not in raw.strip() else None
        if h:
            level = len(h.group(1))
            heads = [x for x in heads if x[0] < level] + [(level, h.group(2).strip())]
        path = " › ".join(t for _, t in heads) or None
        nearest = heads[-1][1] if heads else None
        for a, b in _pieces(text):
            n += 1
            piece = text[a:b]
            if paged and page is not None:
                loc = f"p. {page}"
            elif nearest:
                loc = f"§ {nearest}"
            else:
                loc = f"¶ {n}"
            children.append((Child(text=piece, locator=loc, heading=nearest, char_start=pos[a], char_end=pos[b - 1] + 1,
                                   page=page if paged else None, tokens=count_tokens(piece)), path))
    sections: list[Section] = []
    for ch, path in children:
        cur = sections[-1] if sections else None
        if cur is None or cur.heading_path != path or cur.tokens + ch.tokens > SECTION_TOKENS:
            cur = Section(heading_path=path)
            sections.append(cur)
        cur.children.append(ch)
    return Chunked(sections=sections, pages=max_page if paged else None)
