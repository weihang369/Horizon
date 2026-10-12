"""Work after `turn.end` that never delays the next speaker (docs/ai/01 A13; docs/ai/06 E5; doc 13 W2; turn-plan-emotion
design D18–D24; listener-reactions and face-check specs).

- **Reactions:** one named task per completed AUTO reply with listeners (group, debate, watch). The listeners are read
  from the actor's state when the task runs, never from the turn's frozen context, which may predate a mute or an
  energy change. Each reaction is appended through `actor.emit_checked`, whose check runs under the writer lock, so
  a reaction can never land after its listener's own `turn.start` (D20). The task is dropped (cancelled) by `clear()`,
  a new user message and MANUAL; a failure is logged and never touches the session.
- **The face check (doc 13 W2; D23, D24):** one named task after a completed AUTO reply whose face isn't neutral. It
  asks which emotion the words show and appends one display-only System 1 row with `append_system1` (which drops it
  for a regenerated variant). `clear()` cancels it; a user message and the next turn don't. A late, failed or refused
  check adds nothing and never touches the session.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from horizon.ai.contexts import ListenerView, ReactionRequest, TurnContext
from horizon.ai.naive.noop import NoFaceCheck
from horizon.ai.ports import Reaction
from horizon.domain.timeutil import to_ms
from horizon.sessions.context import characters, energy_of

if TYPE_CHECKING:
    from horizon.runtime import Runtime
    from horizon.sessions.actor import SessionActor, TurnInfo

log = logging.getLogger("horizon.sessions")

Wire = dict[str, Any]
REACTIONS = "reactions"
FACE_CHECK = "face_check"


def _side_label(speaker: Mapping[str, Any] | None, listener: Mapping[str, Any]) -> str | None:
    if speaker is None or not speaker.get("side") or not listener.get("side"):
        return None
    return "same side as the speaker" if speaker["side"] == listener["side"] else "the other side"


async def listener_views(rt: Runtime, actor: SessionActor, speaker_id: str) -> list[ListenerView]:
    """Everyone present but the speaker, read now (D18): `eligible` = unmuted with energy for a reply (asked of Jev);
    the others only fade (E3)."""
    parts = [p for p in actor.session["participants"] if p["characterId"] != speaker_id]
    if not parts:
        return []
    rows = await characters(rt, [p["characterId"] for p in parts])
    est = rt.est_reply_points()
    speaker = next((p for p in actor.session["participants"] if p["characterId"] == speaker_id), None)
    out = []
    for p in parts:
        row = rows.get(p["characterId"])
        if row is None or row["deleted_at"] is not None:
            continue
        energy = float(energy_of(rt, row)["current"])
        profile = row["profile"]
        out.append(ListenerView(id=p["characterId"], name=str(profile.get("name") or p["characterId"]),
                                about_source=str((profile.get("personality") or {}).get("summary") or ""),
                                face=str(p.get("currentEmotion") or "neutral"), side_label=_side_label(speaker, p),
                                eligible=not p.get("mutedByUser") and energy >= est))
    return out


def on_user_message(actor: SessionActor) -> None:
    """D20: a new user message (any mode) drops every pending listener reaction."""
    actor.cancel_background(REACTIONS)


def reaction_check(message_id: str, r: Reaction, fade: frozenset[str]) -> Any:
    """D20's re-check, run under the writer lock just before the append. Also: the session is still active (a leave,
    an end or a cap pause that let the streaming reply finish drops what that reply would set off)."""
    def check(state: Mapping[str, Any]) -> bool:
        s = state["session"]
        if s.get("emotionMode") == "user" or s.get("status") != "active":
            return False
        part = next((p for p in s["participants"] if p["characterId"] == r.character_id), None)
        if part is None or (r.source == "classifier" and part.get("mutedByUser")):
            return False
        msgs = state["messages"]
        streaming = msgs.get(state.get("streamingId") or "")
        if streaming is not None and streaming["author"].get("characterId") == r.character_id:
            return False   # the listener's own turn has started: its reaction is dropped (E5)
        reacted = msgs.get(message_id)
        if reacted is not None and any(m["author"].get("characterId") == r.character_id and m["seq"] > reacted["seq"]
                                       for m in msgs.values()):
            return False   # they have spoken since
        face = str(part.get("currentEmotion") or "neutral")
        if r.source == "default":
            return face in fade   # a fade only moves a face that is still short (E3)
        return face != r.emotion
    return check


def start_reactions(rt: Runtime, actor: SessionActor, info: TurnInfo, ctx: TurnContext, *, key_set: bool) -> None:
    """E5: one named task per completed AUTO reply in a multi-character session."""
    predictor = rt.ai.reactions(key_set)
    fade = rt.runtime_cfg.runtime.emotion_fade
    message_id, speaker_id = info.message_id, info.character_id
    t_end = float(to_ms(rt.clock.now()))
    before = next((m for m in reversed(ctx.session.recent) if m.content and m.id != message_id), None)
    you = str((ctx.session.world.you or {}).get("displayName") or "User")

    async def job() -> None:
        try:
            listeners = await listener_views(rt, actor, speaker_id)
            if not listeners:
                return
            req = ReactionRequest(session=ctx.session, message_id=message_id, speaker_id=speaker_id,
                                  speaker_name=ctx.session.name_of(speaker_id), line=info.content,
                                  before=(f"{you if before.author_type == 'user' else before.name}: {before.content}"
                                          if before is not None else ""),
                                  listeners=listeners, seed=f"{actor.seed}:{ctx.turn_index}")
            reactions = await predictor.predict(req)
            for r in sorted(reactions, key=lambda x: x.delay_ms):
                wait = t_end + r.delay_ms - float(to_ms(rt.clock.now()))
                if wait > 0:
                    await rt.clock.sleep(wait / 1000)
                payload: Wire = {"messageId": message_id, "characterId": r.character_id, "emotion": r.emotion,
                                 "source": r.source}
                if r.p is not None:
                    payload["p"] = r.p
                await actor.emit_checked({"type": "reaction", "payload": payload}, reaction_check(message_id, r, fade))
        except Exception:
            log.exception("reactions failed after message %s (ignored)", message_id)

    actor.background(REACTIONS, job())


def start_face_check(rt: Runtime, actor: SessionActor, info: TurnInfo, ctx: TurnContext, *, key_set: bool) -> None:
    """W2's start conditions past the caller's (complete, not scrubbed, not verbatim): AUTO at `turn.start`, a face that
    isn't neutral, and a profile that checks at all."""
    checker = rt.ai.face_check(key_set)
    face = info.face or "neutral"
    if isinstance(checker, NoFaceCheck) or not info.auto or face == "neutral" or not info.content.strip():
        return
    message_id, variant_id, speaker_id, text = info.message_id, info.variant_id, info.character_id, info.content

    async def job() -> None:
        try:
            out = await checker.check(ctx.session, message_id, speaker_id, face, text)
            if out is None:
                return
            row, call = out
            await actor.append_system1(message_id, variant_id, [row], [call] if call is not None else [])
        except Exception:
            log.exception("the face check failed after message %s (ignored)", message_id)

    actor.background(FACE_CHECK, job())
