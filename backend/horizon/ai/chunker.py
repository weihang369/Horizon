"""The KnowledgeIndexer (doc 05 §2.2; knowledge-memory-storage design D6; doc 10 K1, K12; rag design D3).

`pack@2`: structure first, then length (`count_tokens`, UTF-8 bytes / 3). The MockClient's `paragraphs()` is its twin
on Markdown and text, and both read the shared fixtures in `tests/fixtures/chunker/`.

- **Blocks.** The Markdown splits on blank lines and `<!-- page N -->` marker lines (Docling output) into headings
  (one line each), paragraphs, lists and tables. Paragraph whitespace is collapsed; list and table lines keep their
  line breaks (each line collapsed).
- **Headings are carried forward.** A heading line updates the heading path and goes, as Markdown, at the top of the
  next piece; it is never a piece on its own (a heading at the foot of a page, or two in a row, wait for the next
  content). A piece never crosses a heading change. Headings with no content after them end the document unused.
- **Pages** (paged documents only). A piece never crosses a page marker, unless the paragraph before the marker stops
  mid-sentence (no `. ! ? 。 ！ ？`, closing quotes and brackets allowed after it) and a paragraph follows: the two are
  one paragraph, and its piece's locator is `pp. N–M`.
- **Too small → merge.** Blocks under one heading path and page are packed, joined by a blank line. A piece closes at
  `TARGET` (300) tokens or more, or when the next block would pass `MAX` (400). Tokens count the piece's whole text,
  carried heading lines included.
- **Too large → split.** A block that doesn't fit an empty piece is cut at the sentence end nearest `TARGET` that
  fits; failing that at the last word boundary that fits (`MAX`). Lists are cut between lines, and tables between
  rows, each later part of a table starting with the header row repeated.
- **Locators:** `p. N` or `pp. N–M` for paged documents; else `§ {nearest heading}`; else `¶ {n}`, n the 1-based piece
  number in the source. `heading` is the heading path joined with " › ".
- **Offsets (the invariant).** `char_start` / `char_end` span the piece's first to last block in the Markdown given
  (`extracted.md`). A piece's text, with any repeated table header lines removed, equals the source between them with
  page-marker lines removed, when every whitespace run on both sides is collapsed to one space
  (`tests/unit/test_chunker.py` checks it on every fixture).
- **Sections** (parents, what `naive` reads, K13) are runs of pieces under one heading path, closed near 1 500 tokens.

Chunk sizes are AI-stage tunables (doc 05 §6); changing them bumps `CHUNKER_VERSION`, which makes reindex re-chunk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from horizon.domain.pricing import BYTES_PER_TOKEN, count_tokens

CHUNKER_VERSION = "pack@2"
TOKENIZER = "utf8/4"
TARGET = 300
MAX = 400
SECTION_TOKENS = 1500
_PAGE = re.compile(r"^\s*<!--\s*page\s+(\d+)\s*-->\s*$", re.IGNORECASE)
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_LINE = re.compile(r"[^\r\n]*(?:\r\n|\r|\n)?")   # not `splitlines`: the TS twin splits on these three only
_LIST = re.compile(r"^\s*(?:[-*+]|\d{1,9}[.)])\s+")
_TABLE_SEP = re.compile(r"^[\s|:\-]*-[\s|:\-]*$")
_CLOSERS = "\"'”’)]}»」』"
_SENTENCE = re.compile(r"[.!?][" + re.escape(_CLOSERS) + r"]*(?=\s|$)|[。！？][" + re.escape(_CLOSERS) + r"]*")
_ENDS = (".", "!", "?", "。", "！", "？")
Kind = Literal["heading", "para", "list", "table"]
JOIN = "\n\n"


@dataclass(frozen=True)
class Child:
    text: str
    locator: str
    heading: str | None
    char_start: int
    char_end: int
    page: int | None
    tokens: int
    page_end: int | None = None      # `pp. N–M`: the last page, when it differs from `page`
    repeated: int = 0                # leading characters that repeat a table's header row (outside the offsets)


@dataclass
class Section:
    heading_path: str | None
    children: list[Child] = field(default_factory=list)

    @property
    def text(self) -> str:
        return JOIN.join(c.text for c in self.children)

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
        pages = [c.page_end or c.page for c in self.children if c.page is not None]
        return max(p for p in pages if p is not None) if pages else None


@dataclass(frozen=True)
class Chunked:
    sections: list[Section]
    pages: int | None

    @property
    def children(self) -> list[Child]:
        return [c for s in self.sections for c in s.children]


@dataclass
class _Part:
    """Text with, per character, its offset in the Markdown (−1: a repeated table header, outside the range)."""

    kind: Kind
    text: str
    pos: list[int]
    header: int = 0          # tables: the length of the header lines at the start (0: none)

    def cut(self, a: int, b: int) -> _Part:
        return _Part(self.kind, self.text[a:b], self.pos[a:b])


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


def _lines_part(kind: Kind, lines: list[tuple[int, str]]) -> _Part:
    """A list or table: each line collapsed, joined by newlines."""
    text: list[str] = []
    pos: list[int] = []
    for start, raw in lines:
        t, p = _collapse(raw, start)
        if not t:
            continue
        if text:
            text.append("\n")
            pos.append(pos[-1] + 1)
        text.append(t)
        pos.extend(p)
    part = _Part(kind, "".join(text), pos)
    if kind == "table":
        rows = part.text.split("\n")
        if len(rows) >= 2 and _TABLE_SEP.match(rows[1]):
            part.header = len(rows[0]) + 1 + len(rows[1])
        elif rows:
            part.header = len(rows[0])
    return part


def _line_kind(line: str) -> Kind:
    s = line.strip()
    if s.startswith("|"):
        return "table"
    if _LIST.match(line):
        return "list"
    return "para"


def _blocks(md: str) -> tuple[list[_Part], list[tuple[int, int]]]:
    """The document's blocks in order, and its page markers as (offset, page)."""
    blocks: list[_Part] = []
    markers: list[tuple[int, int]] = []
    cur: list[tuple[int, str]] = []
    kind: Kind = "para"

    def close() -> None:
        nonlocal cur
        if not cur:
            return
        if kind == "para":
            start = cur[0][0]
            raw = md[start:cur[-1][0] + len(cur[-1][1])]
            text, pos = _collapse(raw, start)
            if text:
                blocks.append(_Part("para", text, pos))
        else:
            part = _lines_part(kind, cur)
            if part.text:
                blocks.append(part)
        cur = []

    off = 0
    while off < len(md):
        line = _LINE.match(md, off).group(0)  # type: ignore[union-attr]  # always matches
        body = line.rstrip("\r\n")
        m = _PAGE.match(body)
        if not body.strip() or m:
            close()
            if m:
                markers.append((off, int(m.group(1))))
        elif _HEADING.match(body) is not None:
            close()
            text, pos = _collapse(body, off)
            blocks.append(_Part("heading", text, pos))
        else:
            k = _line_kind(body)
            if cur and not (k == kind or (kind == "list" and k == "para")):
                close()
            if not cur:
                kind = k
            cur.append((off, body))
        off += len(line)
    close()
    return blocks, markers


def _page_at(markers: list[tuple[int, int]], offset: int) -> int | None:
    page: int | None = None
    for at, n in markers:
        if at > offset:
            break
        page = n
    return page


def _stops_mid_sentence(text: str) -> bool:
    return not text.rstrip().rstrip(_CLOSERS).endswith(_ENDS)


def _join_pages(blocks: list[_Part], markers: list[tuple[int, int]]) -> list[_Part]:
    """A paragraph that stops mid-sentence before a page marker runs on into the paragraph after it (paged only)."""
    out: list[_Part] = []
    for b in blocks:
        prev = out[-1] if out else None
        if (prev is not None and prev.kind == "para" and b.kind == "para"
                and _page_at(markers, b.pos[0]) != _page_at(markers, prev.pos[-1])
                and _stops_mid_sentence(prev.text)):
            out[-1] = _Part("para", prev.text + " " + b.text, [*prev.pos, b.pos[0] - 1, *b.pos])
        else:
            out.append(b)
    return out


class _Bytes:
    """UTF-8 byte counts of a text's prefixes, so a cut's tokens cost O(1)."""

    def __init__(self, text: str) -> None:
        self.acc = [0]
        for ch in text:
            self.acc.append(self.acc[-1] + len(ch.encode("utf-8")))

    def tokens(self, base: int, a: int, b: int) -> int:
        n = base + self.acc[b] - self.acc[a]
        return 0 if n == 0 else -(-n // BYTES_PER_TOKEN)


def _split(part: _Part, prefix_bytes: int) -> tuple[_Part, _Part | None]:
    """Cut `part` for an empty piece whose carried text (heading lines and their join) is `prefix_bytes` long: the head
    fits within `MAX` tokens; the rest is returned for the next piece."""
    text = part.text
    bc = _Bytes(text)

    def fits(c: int) -> bool:
        return bc.tokens(prefix_bytes, 0, c) <= MAX

    def nearest(cands: list[int]) -> int | None:
        ok = [c for c in cands if 0 < c < len(text) and fits(c)]
        return min(ok, key=lambda c: (abs(bc.tokens(prefix_bytes, 0, c) - TARGET), c)) if ok else None

    cut: int | None = None
    if part.kind in ("list", "table"):
        lo = part.header if part.kind == "table" else 0
        cut = nearest([i for i, ch in enumerate(text) if ch == "\n" and i > lo])
    if cut is None:
        cut = nearest([m.end() for m in _SENTENCE.finditer(text)])
    if cut is None:
        spaces = [i for i, ch in enumerate(text) if ch in " \n" and i > 0 and fits(i)]
        cut = spaces[-1] if spaces else None
    if cut is None:
        cut = max(1, max((c for c in range(1, len(text)) if fits(c)), default=1))
    head = part.cut(0, cut)
    head.text = head.text.rstrip()
    head.pos = head.pos[:len(head.text)]
    a = cut
    while a < len(text) and text[a].isspace():
        a += 1
    if a >= len(text):
        return head, None
    rest = part.cut(a, len(text))
    if part.kind == "table" and part.header and cut > part.header:
        hdr = text[:part.header]
        rest = _Part("table", hdr + "\n" + rest.text, [-1] * (len(hdr) + 1) + rest.pos, header=len(hdr))
    return head, rest


@dataclass
class _Piece:
    heads: list[_Part]
    path: str | None
    nearest: str | None
    parts: list[_Part] = field(default_factory=list)

    def text(self, extra: _Part | None = None) -> str:
        return JOIN.join(p.text for p in [*self.heads, *self.parts, *([extra] if extra else [])])

    def prefix_bytes(self) -> int:
        """The carried text before a part placed into this (content-free) piece."""
        if not self.heads:
            return 0
        return len((JOIN.join(h.text for h in self.heads) + JOIN).encode("utf-8"))


def chunk(markdown: str, *, paged: bool = False) -> Chunked:
    md = markdown
    blocks, markers = _blocks(md)
    if paged:
        blocks = _join_pages(blocks, markers)
    heads: list[tuple[int, str]] = []
    pending: list[_Part] = []
    pieces: list[_Piece] = []
    cur: _Piece | None = None

    def page_of(p: _Part, last: bool = False) -> int | None:
        real = [x for x in p.pos if x >= 0]
        return _page_at(markers, real[-1] if last else real[0]) if paged and real else None

    def close() -> None:
        nonlocal cur
        if cur is not None and cur.parts:
            pieces.append(cur)
        cur = None

    for b in blocks:
        if b.kind == "heading":
            close()
            h = _HEADING.match(b.text)
            assert h is not None
            level = len(h.group(1))
            heads = [x for x in heads if x[0] < level] + [(level, h.group(2).strip())]
            pending.append(b)
            continue
        if cur is not None and cur.parts and paged and page_of(b) != page_of(cur.parts[-1], last=True):
            close()
        rest: _Part | None = b
        while rest is not None:
            if cur is None:
                path = " › ".join(t for _, t in heads) or None
                cur = _Piece(heads=pending, path=path, nearest=heads[-1][1] if heads else None)
                pending = []
            if count_tokens(cur.text(rest)) <= MAX:
                cur.parts.append(rest)
                rest = None
                if count_tokens(cur.text()) >= TARGET:
                    close()
            elif cur.parts:
                close()
            else:
                head, rest = _split(rest, cur.prefix_bytes())
                cur.parts.append(head)
                close()
    close()

    children: list[tuple[Child, str | None]] = []
    max_page: int | None = None
    for n, pc in enumerate(pieces, start=1):
        text = pc.text()
        real = [x for part in [*pc.heads, *pc.parts] for x in part.pos if x >= 0]
        content = [x for part in pc.parts for x in part.pos if x >= 0]
        p0 = _page_at(markers, content[0]) if paged else None
        p1 = _page_at(markers, content[-1]) if paged else None
        if p1 is not None:
            max_page = p1 if max_page is None else max(max_page, p1)
        if paged and p0 is not None:
            loc = f"p. {p0}" if p1 in (None, p0) else f"pp. {p0}–{p1}"
        elif pc.nearest:
            loc = f"§ {pc.nearest}"
        else:
            loc = f"¶ {n}"
        lead = pc.parts[0].pos if not pc.heads else []
        repeated = next((i for i, x in enumerate(lead) if x >= 0), 0)
        children.append((Child(text=text, locator=loc, heading=pc.path, char_start=min(real), char_end=max(real) + 1,
                               page=p0, tokens=count_tokens(text), page_end=p1 if p1 != p0 else None,
                               repeated=repeated), pc.path))
    sections: list[Section] = []
    for ch, path in children:
        sec = sections[-1] if sections else None
        if sec is None or sec.heading_path != path or sec.tokens + ch.tokens > SECTION_TOKENS:
            sec = Section(heading_path=path)
            sections.append(sec)
        sec.children.append(ch)
    if paged and markers:
        max_page = max(max_page or 0, max(n for _, n in markers))
    return Chunked(sections=sections, pages=max_page if paged else None)

