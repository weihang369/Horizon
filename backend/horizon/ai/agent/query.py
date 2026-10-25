"""What an `agent` deep turn searches (doc 10 K4; rag design D10; deep-turn "The query is built at the gate, in
parallel"; retrieval "Agent keyword terms").

- **Keyword terms** (`agent_terms`): Unicode words of 2+ characters, lower-cased, without FTS operators and without
  the committed English stop list, de-duplicated, without words no searchable piece of the speaker's holds, ordered
  rarest first within those pieces (one scoped FTS5 count per term, at most 40 looked at), cut to 16, or 24 with a
  rewrite (its terms first, then the message's). The FTS query keeps today's quoted OR form, so user text still
  can't change how the search works.
- **The bundle per case** (K4's table): as written, rewritten, a failed or late rewrite (marked `fallback`), debate
  (the motion and the last opposing argument, or the motion alone for an opening, or the moderator's question and the
  motion for an Ask answer) and watch (the last message, and the two earlier lines with it).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from horizon.ai.retrieval import DISPLAY_MAX, QueryBundle, QuerySource, ScopedIndex

MAX_TERMS = 16
MAX_TERMS_REWRITTEN = 24
LOOKED_AT = 40
FEW_TERMS = 3
_WORD = re.compile(r"\w+", re.UNICODE)
_OPERATORS = frozenset({"and", "or", "not", "near"})
# A committed English stop list (≈ 180 words): function words and chat filler that every passage holds.
STOP_WORDS: frozenset[str] = frozenset("""
a about above after again against all also am an any are aren as at be because been before being below between both
but by can cannot could couldn did didn do does doesn doing don down during each else even ever every few for from
further get gets getting got had hadn has hasn have haven having he her here hers herself him himself his how however
i if in into is isn it its itself just let ll may me might more most much must mustn my myself need no nor now of off
often on once only other ought our ours ourselves out over own please quite rather re really same say says said shall
shan she should shouldn so some such tell than that the their theirs them themselves then there these they this those
though through thus to too under until up upon us ve very via was wasn we well were weren what whatever when where
whether which while who whom whose why will with within without won would wouldn yes yet you your yours yourself
yourselves okay ok hey hi hello thanks thank like think know want wants going gonna wanna kind sort thing things
something anything everything nothing way ways lot lots bit maybe perhaps actually basically
""".split())


def words(text: str) -> list[str]:
    """The text's searchable words: 2+ characters, lower-cased, no operators, no stop words, first occurrence order."""
    out: list[str] = []
    for w in _WORD.findall(text.lower()):
        w = w.replace("_", "")
        if len(w) >= 2 and w not in _OPERATORS and w not in STOP_WORDS and w not in out:
            out.append(w)
    return out


async def rarest(index: ScopedIndex, terms: Sequence[str]) -> list[str]:
    """`terms` (at most 40 looked at) that some of the speaker's pieces hold, ordered by how few hold each, ties in
    their own order. A term no piece holds can't match, and it sorted first: a debate rebuttal's text (the motion and
    the whole opposing argument) filled all 16 slots with them, so its search found nothing (U-34)."""
    look = list(terms)[:LOOKED_AT]
    if not look:
        return []
    counts = await index.term_counts(look)
    pos = {t: i for i, t in enumerate(look)}
    return sorted((t for t in look if counts.get(t, 0) > 0), key=lambda t: (counts[t], pos[t]))


async def agent_terms(index: ScopedIndex, message: str, *, rewrite: str | None = None,
                      extra: str = "") -> list[str]:
    """The BM25 terms: the rewrite's first, then the message's (`extra`: the previous user message, for a failed rewrite
    with fewer than 3 terms)."""
    if rewrite:
        first = await rarest(index, words(rewrite))
        rest = await rarest(index, [w for w in words(message) if w not in first])
        return (first + rest)[:MAX_TERMS_REWRITTEN]
    own = await rarest(index, words(message))
    if extra and len(own) < FEW_TERMS:
        own += await rarest(index, [w for w in words(extra) if w not in own])
    return own[:MAX_TERMS]


def fts_or(terms: Sequence[str]) -> str | None:
    """The quoted OR form (each term double-quoted, so it is a plain word to FTS5)."""
    clean = [t.replace('"', "") for t in terms if t.replace('"', "")]
    return " OR ".join(f'"{t}"' for t in clean) if clean else None


def display(text: str) -> str:
    one = " ".join(text.split())
    return one if len(one) <= DISPLAY_MAX else one[:DISPLAY_MAX - 1].rstrip() + "…"


def bundle(*, source: QuerySource, mode: str, speaker_id: str, message: str, message_id: str | None,
           earlier: Sequence[str] = (), rewrite: str | None = None, terms: Sequence[str] = (),
           dense: dict[str, dict[int, list[float]]] | None = None,
           waits: dict[str, float] | None = None) -> QueryBundle:
    """The frozen bundle for one search, K4's table:

    | source | dense texts |
    |---|---|
    | as_written | the message |
    | rewritten | the rewrite, the message |
    | fallback | the message, the two earlier lines + the message |
    | debate | the debate text (motion + argument, the motion, or the question + motion) |
    | watch | the last message, the two earlier lines + it |
    """
    with_earlier = "\n".join([*earlier, message]) if earlier else ""
    if source == "rewritten" and rewrite:
        texts: tuple[str, ...] = (rewrite, message)
    elif source in ("fallback", "watch") and with_earlier:
        texts = (message, with_earlier)
    else:
        texts = (message,)
    return QueryBundle(text=rewrite or message, message_id=message_id, speaker_id=speaker_id, mode=mode, source=source,
                       message=message, rewrite=rewrite if source == "rewritten" else None, earlier=tuple(earlier),
                       dense_texts=texts, terms=tuple(terms), dense=dict(dense or {}),
                       display=display(rewrite if source == "rewritten" and rewrite else message),
                       waits=dict(waits or {}))


def debate_text(motion: str, *, argument: str = "", question: str = "") -> str:
    """D8/D10: a rebuttal, closing or panel turn searches the motion and the last opposing argument; an opening the
    motion; an Ask answer the moderator's question and the motion."""
    if question:
        return f"{question}\n{motion}"
    return f"{motion}\n{argument}" if argument else motion


def earlier_lines(recent: Sequence[Any], before_id: str | None, you: str, n: int = 2) -> list[str]:
    """The `n` lines before the message `before_id` (or before the end), as "Name: text"."""
    lines = [m for m in recent if getattr(m, "content", "") and getattr(m, "author_type", "") in ("user", "character")]
    if before_id is not None:
        idx = next((i for i, m in enumerate(lines) if m.id == before_id), len(lines))
        lines = lines[:idx]
    return [f"{you if m.author_type == 'user' else m.name}: {m.content}" for m in lines[-n:]]
