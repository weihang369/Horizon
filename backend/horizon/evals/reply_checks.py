"""The reply-rule code checks, $0 (docs/ai/04 P8, P12; doc 02 B1, B4; evaluation-harness "Reply-rule checks";
persona-context design D28).

Run on every evaluated reply. `long` uses them in M8; `conversations` (M15) reuses them. The repetition rates are
measured on free-running conversations only (P8: on frozen transcripts the earlier replies aren't the agent's own).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

ACTION = re.compile(r"\*(?=\S)[^*\n]{1,80}(?<=\S)\*")   # *smiles*, never "2 * 3 * 4"
STRAY_TAG = re.compile(r"<\s*e\s*:[^>]{0,30}>", re.I)
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]")
BUBBLE_TARGET = {"one_on_one": 3, "group": 2, "watch": 2, "debate": 1}
OPENER_WORDS = 3
OPENER_LOOKBACK = 3


@dataclass(frozen=True)
class Reply:
    """One evaluated reply: who said it, in which mode, the text, and the speaker's catchphrases."""

    speaker: str
    mode: str
    text: str
    names: tuple[str, ...] = ()          # the speaker's own names, for the name-prefix check
    catchphrases: tuple[str, ...] = ()


@dataclass
class ReplyStats:
    n: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    flagged: dict[str, list[int]] = field(default_factory=dict)   # check -> indices of the replies it flagged

    def add(self, check: str, i: int, hit: bool) -> None:
        self.counts.setdefault(check, 0)
        if hit:
            self.counts[check] += 1
            self.flagged.setdefault(check, []).append(i)

    def rate(self, check: str) -> float | None:
        return self.counts.get(check, 0) / self.n if self.n else None

    def summary(self) -> dict[str, Any]:
        return {"n": self.n, **{k: {"count": v, "rate": round(v / self.n, 4) if self.n else None}
                               for k, v in sorted(self.counts.items())}}


def lines(text: str) -> list[str]:
    return [x for x in text.split("\n") if x.strip()]


OPEN_TAG = re.compile(r"<e:[^<>]{0,30}>")
CLOSE_TAG = re.compile(r"</e:[^<>]{0,30}>")


def note_in_tag(raw: str) -> bool:
    """M11 debate D31.3, M15 D14: `naive` wrote a note inside its emotion tag (`<e:thinking>` … `</e:thinking>`) or a
    stray tag after the first: any closing tag, or a second opening tag. Read on the model's raw reply, before the
    parser strips them; `agent` writes no tags."""
    return bool(CLOSE_TAG.search(raw)) or len(OPEN_TAG.findall(raw)) > 1


def has_action(text: str) -> bool:
    return bool(ACTION.search(text))


def has_stray_tag_or_prefix(text: str, names: Sequence[str]) -> bool:
    if STRAY_TAG.search(text):
        return True
    for line in lines(text):
        low = line.strip().casefold()
        if any(re.match(re.escape(n.casefold()) + r"[ \t]*:", low) for n in names if n):
            return True
    return False


def over_bubbles(text: str, mode: str) -> bool:
    return len(lines(text)) > BUBBLE_TARGET.get(mode, 3)


def emoji_count(text: str) -> int:
    return len(EMOJI.findall(text))


def ends_with_question(text: str) -> bool:
    t = text.rstrip().rstrip("\"'”’)")
    return t.endswith(("?", "？"))


def opener(text: str) -> str:
    words = re.findall(r"[\w']+", text.casefold())
    return " ".join(words[:OPENER_WORDS])


def check_replies(replies: Sequence[Reply], *, free_running: bool) -> ReplyStats:
    """Every code check of P12 over `replies` in conversation order. The two repetition rates only when free running."""
    st = ReplyStats(n=len(replies))
    previous: dict[str, list[str]] = {}
    for i, r in enumerate(replies):
        st.add("actions", i, has_action(r.text))
        st.add("stray_tag_or_prefix", i, has_stray_tag_or_prefix(r.text, r.names))
        st.add("over_bubbles", i, over_bubbles(r.text, r.mode))
        st.add("emoji_over_one", i, emoji_count(r.text) > 1)
        st.add("question_ending", i, ends_with_question(r.text))
        if free_running:
            mine = previous.setdefault(r.speaker, [])
            op = opener(r.text)
            st.add("repeated_opener", i, bool(op) and op in mine[-OPENER_LOOKBACK:])
            mine.append(op)
            low = r.text.casefold()
            st.add("catchphrase", i, any(c.strip().casefold() in low for c in r.catchphrases if c.strip()))
    return st


def step_two_rate(cuts: Iterable[Mapping[str, Any]]) -> float | None:
    """P12: how often P4's step 2 fired, over the cards' cut reports (`PersonaPrompt.cut`)."""
    xs = list(cuts)
    return sum(1 for c in xs if c.get("step2")) / len(xs) if xs else None


TARGETS = {"actions": 0.02, "stray_tag_or_prefix": 0.02, "question_ending": 0.5, "repeated_opener": 0.10,
           "catchphrase": 0.20, "step2": 0.01}   # P8, P12: each rate must stay under its target
