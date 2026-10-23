"""`agent` listener reactions: one Jev request after `turn.end`, and the code rule for what shows (docs/ai/06 E3, E5;
turn-plan-emotion design D18–D21; listener-reactions spec).

- **One request, one question per listener** (`reaction`, keyed `reaction:{listenerId}`): the 7 emotions plus `none`
  ("no visible reaction"), each listener named, with a seed derived as `"{turn seed}:react:{listenerId}"`. The state
  names each listener and their card line but not their face (D37).
- **The keep rule (code, E5):** a pick that isn't `none`, with Jev's confidence at or above the floor (on a neutral
  face, `neutral` and `none` merge first, as for the speaker), whose face differs from the listener's face. At most
  the 2 most confident show. The runtime re-checks "differs" under the writer lock just before each append (D20).
- **Fades (E3), outside the cap:** a listener whose face is short (surprised, embarrassed) and who gets no reaction
  from this pass gets `neutral` with source `default` and no `p`. Muted and exhausted characters get the fade only,
  never a Jev question; a failed or late call still gives the fades (they need no Jev).
- **Timing:** each shown reaction plays at a seeded delay in the timing table's `reactionDelayMs` after `turn.end`, or
  as soon as Jev answers if that is later (the task waits for the later of the two).
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import Any

from horizon.ai.agent.emotion import NONE, decide_face
from horizon.ai.agent.plan_state import ABOUT_MAX, cut_tokens, first_sentence, head_tail
from horizon.ai.contexts import ListenerView, ReactionRequest
from horizon.ai.decider import Answers, ChoiceAnswer, DecisionResult
from horizon.ai.ports import Reaction
from horizon.ai.questions import bank

log = logging.getLogger("horizon.ai.reactions")

PURPOSE = "reaction"
QUESTION = "reaction"
KEEP = 2
LINE_MAX, LINE_HEAD, LINE_TAIL = 600, 450, 150
BEFORE_MAX = 300
NAME_MAX = 40


def delay_ms(seed: str, listener_id: str, window: tuple[float, float]) -> float:
    """One seeded delay per listener in `reactionDelayMs` (E5): the same turn always plays the same way."""
    return random.Random(f"{seed}:react:{listener_id}:delay").uniform(window[0], window[1])


def keep(answers: Mapping[str, ChoiceAnswer | None], listeners: Sequence[ListenerView], *, floor: float,
         fade: frozenset[str], seed: str, window: tuple[float, float]) -> list[Reaction]:
    """E5's rule plus E3's fades. `answers` maps a listener's ID to Jev's answer (None or missing: no answer). Each
    listener's answer goes through the speaker's rule (`decide_face`: the merge on a neutral face, the floor, the
    fade), with the listener's face as the base: a confident face that differs is a reaction; a kept short face fades."""
    picks: list[tuple[float, Reaction]] = []
    fades: list[Reaction] = []
    for lv in listeners:
        a = answers.get(lv.id) if lv.eligible else None
        f = decide_face(a, base=lv.face, floor=floor, fade=fade)
        if f.source == "classifier" and f.face != lv.face:
            value = float(f.compared[0]["value"]) if f.compared else float(f.p or 0.0)
            picks.append((value, Reaction(character_id=lv.id, emotion=f.face, p=f.p,
                                          delay_ms=delay_ms(seed, lv.id, window))))
        elif f.faded:
            fades.append(Reaction(character_id=lv.id, emotion="neutral", p=None,
                                  delay_ms=delay_ms(seed, lv.id, window), source="default"))
    picks.sort(key=lambda x: -x[0])
    return [r for _, r in picks[:KEEP]] + fades   # E3: fades go outside the cap


def state(req: ReactionRequest) -> dict[str, Any]:
    """E5's state with doc 11 S6's names: the line and the line before it as quoted text, the listeners, the mode."""
    listeners = []
    for lv in req.listeners:
        if not lv.eligible:
            continue
        # D37 (the maintainer's choice): no face here. With it, Jev answered the face the listener already had in 83 of
        # 90 items; code still compares with it ("differs") and fades by it
        entry: dict[str, Any] = {"name": lv.name, "about": cut_tokens(first_sentence(lv.about_source), ABOUT_MAX)}
        if lv.side_label:
            entry["side"] = lv.side_label
        listeners.append(entry)
    out: dict[str, Any] = {"mode": req.session.mode,
                           "quoted_line": head_tail(f"{req.speaker_name}: {req.line}", LINE_MAX, LINE_HEAD, LINE_TAIL),
                           "quoted_listeners": listeners}
    if req.before:
        out["quoted_before"] = cut_tokens(req.before, BEFORE_MAX)
    return out


def _name(full: str) -> str:
    return full if len(full) <= NAME_MAX else full.split(" ")[0][:NAME_MAX]


class JevReactions:
    """The `agent` reaction predictor (D18): async, called inside the reactions task, never in `finish`."""

    def __init__(self, deps: Any) -> None:
        self.deps = deps

    async def predict(self, req: ReactionRequest) -> list[Reaction]:
        window = self.deps.timing.reaction_delay_ms
        fade = self.deps.emotion_fade()
        entry = bank().get(QUESTION)
        floor = entry.floor if entry.floor is not None else 0.6
        asked = [lv for lv in req.listeners if lv.eligible]
        if not asked:
            return keep({}, req.listeners, floor=floor, fade=fade, seed=req.seed, window=window)
        questions = {f"{QUESTION}:{lv.id}": bank().question(QUESTION, seed=f"{req.seed}:react:{lv.id}",
                                                              name=_name(lv.name), about=lv.id) for lv in asked}

        async def fallback() -> Answers:
            return {k: ChoiceAnswer(NONE) for k in questions}

        decider = self.deps.decider()
        ctx = req.session.call_ctx(PURPOSE, character_id=req.speaker_id, message_id=req.message_id)
        answers: dict[str, ChoiceAnswer | None] = {}
        call = None
        try:
            call = decider.start(state(req), questions, ctx, purpose=PURPOSE, fallback=fallback)
            res: DecisionResult = await call.by(decider.now() + timedelta(seconds=decider.timeout_for(PURPOSE)))
            for lv in asked:
                a = res.answers.get(f"{QUESTION}:{lv.id}")
                answers[lv.id] = a if isinstance(a, ChoiceAnswer) else None
        except asyncio.CancelledError:
            if call is not None:
                call.cancel()   # D20: dropped (a user message, Stop…): readers detach, the request settles
            raise
        except Exception:   # E5: a failure never touches the session; the fades still play
            log.exception("the reaction call failed for message %s (fades only)", req.message_id)
        return keep(answers, req.listeners, floor=floor, fade=fade, seed=req.seed, window=window)
