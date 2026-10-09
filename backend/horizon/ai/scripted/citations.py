"""Scripted knowledge citations: a port of `mock/script/citations.ts` (D-59; knowledge-memory-storage design D15).

The scripted turn engine cites the passages the runtime retrieved for the speaker, as the MockClient's live engine
cites a character's indexed knowledge: about 55 % of replies with hits cite 1–2 passages (best word overlap with the
prompt and reply first), and one more passage is retrieved but not used. It draws from its **own RNG stream**
(`{seed}:{turn}:cite`), so a character without hits replies exactly as before. Memory hits are never used (parity
with the mock).
"""

from __future__ import annotations

import random
import re
from typing import Any

from horizon.ai.contexts import KnowledgeHit

QUOTE_MAX = 400
QUERY_MAX = 120
CITE_CHANCE = 0.55
TWO_CHANCE = 0.4
_SENTENCE_END = re.compile(r"[.!?…](?=\s|$)")
_WORD = re.compile(r"[a-z]{4,}")


def hash_string(s: str) -> int:
    """`rng.ts` hashString (FNV-1a over UTF-16 code units)."""
    h = 2166136261
    data = s.encode("utf-16-le")
    for i in range(0, len(data), 2):
        h ^= data[i] | (data[i + 1] << 8)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def _r2(n: float) -> float:
    return int(n * 100 + 0.5) / 100


def passage_score(key: str, chunk_id: str, cited: bool) -> float:
    u = (hash_string(f"{key}:{chunk_id}") % 1000) / 1000
    return _r2(0.74 + u * 0.19) if cited else _r2(0.46 + u * 0.22)


def _entry(h: KnowledgeHit) -> dict[str, Any]:
    return {"chunkId": h.chunk_id, "sourceId": h.source_id, "title": h.title,
            **({"locator": h.locator} if h.locator else {}), "text": h.text}


def cite_knowledge(key: str, cited: list[KnowledgeHit], uncited: list[KnowledgeHit],
                   query: str | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """`cited[i]` backs marker `[i + 1]`; `uncited` are retrieved but not used. Returns (citations, trace.knowledge)."""
    citations = [{"n": i + 1, "sourceId": h.source_id, "title": h.title, "type": h.type, "chunkId": h.chunk_id,
                  **({"locator": h.locator} if h.locator else {}),
                  "quote": h.text if len(h.text) <= QUOTE_MAX else h.text[:QUOTE_MAX - 1] + "…",
                  "score": passage_score(key, h.chunk_id, True)} for i, h in enumerate(cited)]
    retrieved = [{**_entry(h), "score": citations[i]["score"], "cited": True, "n": i + 1} for i, h in enumerate(cited)]
    retrieved += [{**_entry(h), "score": passage_score(key, h.chunk_id, False), "cited": False} for h in uncited]
    retrieved.sort(key=lambda r: -float(r["score"]))
    return citations, {**({"query": query} if query else {}), "trigger": "always", "retrieved": retrieved}


def insert_markers(text: str, count: int) -> str:
    """`[1]..[count]` after the `count` longest sentences (in reading order), or at the end of the text."""
    ends: list[tuple[int, int]] = []
    last = 0
    for m in _SENTENCE_END.finditer(text):
        at = m.end()
        ends.append((at, at - last))
        last = at
    picked = sorted(sorted(ends, key=lambda e: -e[1])[:count])
    out, start = "", 0
    for i, (at, _) in enumerate(picked):
        out += f"{text[start:at]}[{i + 1}]"
        start = at
    out += text[start:]
    for n in range(len(picked) + 1, count + 1):
        out = f"{out.rstrip()}[{n}]"
    return out


def _words(t: str) -> set[str]:
    return {w.removesuffix("s") for w in _WORD.findall(t.lower())}


def _rank(pool: list[KnowledgeHit], query: str, rng: random.Random) -> list[KnowledgeHit]:
    q = _words(query)
    shuffled = list(pool)
    rng.shuffle(shuffled)
    scored = [(sum(1 for w in _words(f"{h.text} {h.title}") if w in q), i, h) for i, h in enumerate(shuffled)]
    return [h for _, _, h in sorted(scored, key=lambda x: (-x[0], x[1]))]


def live_citations(key: str, text: str, prompt: str, pool: list[KnowledgeHit],
                   rng: random.Random) -> tuple[str, list[dict[str, Any]], dict[str, Any]] | None:
    """Maybe cite some of `pool`: (text with markers, citations, trace.knowledge), or None."""
    if not pool or rng.random() >= CITE_CHANCE:
        return None
    picked = _rank(pool, f"{prompt} {text}", rng)
    count = min(len(picked), 2 if rng.random() < TWO_CHANCE else 1)
    sentences = len(re.findall(r"[.!?…](\s|$)", text))
    n = max(1, min(count, sentences or 1))
    query = prompt.strip()[:QUERY_MAX] or None
    citations, knowledge = cite_knowledge(key, picked[:n], picked[n:n + 1], query)
    return insert_markers(text, n), citations, knowledge
