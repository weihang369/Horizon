"""The scripted line bank (session-runtime design D10, OQ-12): deterministic, Python-native, not byte-identical with
the MockClient's TS banks (no test compares text).

Lines are templates over the character's profile, picked with `random.Random(seed)`, where the seed is
`"{sessionId}:{turn}"`, so the same session state always yields the same line. Chat lines run to two sentences, so a
reply is long enough for the `stream_cut` fault (24 tokens) to land mid-stream.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any

EMOTIONS = ("neutral", "happy", "sad", "angry", "surprised", "thinking", "embarrassed")


@dataclass(frozen=True)
class Line:
    text: str
    emotion: str


def first_name(name: str) -> str:
    words = [w for w in name.split(" ") if w.rstrip(".").lower() not in ("dr", "prof", "mr", "ms", "mrs")]
    return words[0] if words else name


def _field(profile: dict[str, Any]) -> str:
    expertise = profile.get("expertise") or []
    return str(expertise[0]) if expertise else str(profile.get("role") or "my line of work").lower()


def greeting(profile: dict[str, Any]) -> Line:
    text = str(profile.get("greeting") or "")
    return Line(text or f"Hi, I'm {first_name(str(profile.get('name', '')))}. What's on your mind today?", "happy")


def _topic(prompt: str) -> str:
    words = [w for w in re.findall(r"[A-Za-z']+", prompt) if len(w) > 3]
    return " ".join(words[:4]).lower() if words else "this"


def chat_lines(profile: dict[str, Any], prompt: str) -> list[Line]:
    field = _field(profile)
    role = str(profile.get("role") or "someone in my position").lower()
    tagline = str(profile.get("tagline") or "Let's take it one step at a time.")
    quips = (profile.get("speakingStyle") or {}).get("catchphrases") or []
    quip = str(quips[0]) if quips else "Okay, you got me there."
    topic = _topic(prompt)
    return [
        Line(f"Good question about {topic}. As {_article(role)} {role}, I'd start with one thing: what would a good "
             f"outcome look like for you, and what has already been tried?", "thinking"),
        Line(f"{tagline} With {topic}, the details matter more than the headline, so tell me what changed recently and "
             f"when you first noticed it.", "neutral"),
        Line(f"Oh, that's interesting. In {field}, things like {topic} almost never go the way people expect, so let's "
             f"slow down and look at the evidence before deciding anything.", "surprised"),
        Line(f"{quip} Sorry, I had to say it. But seriously, {topic} deserves a proper answer, and I'd rather be honest "
             f"about what I don't know than guess.", "embarrassed"),
        Line(f"That's genuinely good to hear. Tell me more about {topic}: what worked, what surprised you, and what you "
             f"would do differently next time?", "happy"),
        Line(f"That sounds hard, and I'm listening. Take your time with {topic}; we can go through it piece by piece, and "
             f"nothing has to be decided tonight.", "sad"),
    ]


def _article(word: str) -> str:
    return "an" if word[:1] in "aeiou" else "a"


_PHASE: dict[str, list[tuple[str, str]]] = {
    "opening": [
        ("Let me set out the {side} case plainly. \"{motion}\" is not a slogan; it is a trade-off, and the benefits are "
         "larger than the costs once you count them honestly.", "neutral"),
        ("Three things decide this motion: who pays, who benefits, and how fast it can be undone. On all three, the "
         "{side} side holds, and I'll show you why.", "thinking"),
        ("Before anyone gets carried away: \"{motion}\" sounds simple. The evidence for it is narrower than its "
         "supporters admit, and that matters tonight.", "thinking"),
    ],
    "rebuttal": [
        ("My opponents describe the best case and call it the expected case. The {side} position simply asks what "
         "happens on an ordinary Tuesday, when nothing goes to plan.", "angry"),
        ("That example was vivid, I'll give it that. But a vivid example is not a representative one, and policy has "
         "to work for the representative case.", "thinking"),
        ("Honestly? I agree with half of that. It's the other half that sinks the argument, and the {side} side has "
         "named that half twice already.", "surprised"),
    ],
    "closing": [
        ("So where are we? The {side} side has shown its costs are real and measurable. Weigh that carefully before "
         "you accept \"{motion}\".", "neutral"),
        ("Strip away the rhetoric and one question is left: who carries the risk if we're wrong? Answer that "
         "honestly, and you have your verdict.", "thinking"),
        ("I came in sceptical and I leave sceptical, but better informed. That's the most honest closing the {side} "
         "side can give you tonight.", "happy"),
    ],
}


def debate_line(phase: str, motion: str, side: str | None, index: int) -> Line:
    label = "proposition" if side == "prop" else "opposition" if side == "opp" else "panel"
    lines = _PHASE.get(phase, _PHASE["opening"])
    text, emotion = lines[index % len(lines)]
    m = re.sub(r"^this house (would|believes)\s*", "", motion, flags=re.IGNORECASE)
    return Line(text.format(side=label, motion=m), emotion)


def answer_to(question: str) -> Line:
    return Line(f"You asked: \"{question[:80]}\". Direct answer: it depends on the assumptions, and I'll name mine so "
                f"you can attack them.", "thinking")


def scene_lines(profile: dict[str, Any], premise: str) -> list[Line]:
    name = first_name(str(profile.get("name", "")))
    head = premise.split(".")[0] or premise
    return [
        Line(f"{head}. Of course this would happen today, of all days.", "neutral"),
        Line("Well, nobody told me there'd be a plot twist this afternoon.", "surprised"),
        Line(f"{name} sighs. Fine. Let's see where this one goes.", "thinking"),
        Line("Okay, that was actually kind of nice. Don't tell anyone I said so.", "happy"),
        Line(f"You know what, {name} has a better idea. Hear me out for a second.", "thinking"),
    ]


def direction_lines(note: str) -> list[Line]:
    n = note.rstrip(".").lower()
    return [
        Line(f"Wait, {n}? That changes everything about this afternoon.", "surprised"),
        Line(f"Huh. {note.rstrip('.')}. I really didn't see that coming.", "thinking"),
        Line(f"Of course {n}. Of course it does, today of all days.", "angry"),
    ]


def pick_line(kind: str, profile: dict[str, Any], *, rng: random.Random, prompt: str = "", recent: list[str] | None = None,
              motion: str = "", side: str | None = None, phase: str = "opening", index: int = 0,
              premise: str = "", note: str | None = None) -> Line:
    """The line for one turn. `recent` texts are avoided while fresh lines remain (the mock's rule)."""
    if kind == "greeting":
        return greeting(profile)
    if kind == "debate":
        return debate_line(phase, motion, side, index)
    if kind == "answer":
        return answer_to(prompt)
    if kind == "scene":
        pool = direction_lines(note) if note else scene_lines(profile, premise)
    else:
        pool = chat_lines(profile, prompt)
    seen = set(recent or [])
    fresh = [x for x in pool if x.text not in seen]
    return rng.choice(fresh or pool)
