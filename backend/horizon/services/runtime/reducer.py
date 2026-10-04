"""The session reducer: a literal port of `frontend/src/engine/sessionReducer.ts` (D-79, doc 02 §3.4).

Session events are the source of truth; messages, participant state and session state are derived by this
function. Both languages are pinned by `backend/tests/fixtures/reducer/*.json` and by
`reduce(seed events) == seed messages`.

Port rules:
- State and messages are plain wire-shaped dicts. A TS property set to `undefined` is a *missing key* here,
  because both sides compare in JSON form (`JSON.stringify` drops undefined).
- `round6` reproduces JS `Math.round` (half rounds up, toward +∞), not Python's banker's rounding.
- `apply_event` is pure (it copies); `reduce_all` copies once and then applies in place, and deep-copies each
  event payload so the caller's events are never mutated.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Iterable
from typing import Any

State = dict[str, Any]
Event = dict[str, Any]
Msg = dict[str, Any]


def _put(d: dict[str, Any], key: str, value: Any) -> None:
    """Assign like a TS object spread: `None` stands for `undefined`, which removes the key."""
    if value is None:
        d.pop(key, None)
    else:
        d[key] = value


def round6(n: float) -> float:
    return math.floor(n * 1e6 + 0.5) / 1e6


def initial_runtime(session: dict[str, Any], messages: Iterable[Msg] = ()) -> State:
    msgs = [copy.deepcopy(m) for m in messages]
    order = [m["id"] for m in sorted(msgs, key=lambda m: m["seq"])]
    session = copy.deepcopy(session)
    st = session.get("state")
    s: State = {
        "session": session,
        "messages": {m["id"]: m for m in msgs},
        "order": order,
        "displayEmotion": {p["characterId"]: p["currentEmotion"] for p in session["participants"]},
        "pendingEmotion": {},
        "energyById": {},
        "phase": {"phase": st["phase"], "round": st["round"], "iteration": st["iteration"]}
        if st and "phase" in st else None,
        "watch": None,
        "paused": session["status"] == "paused",
        "errors": [],
        "lastSeq": 0,
    }
    _put(s, "nextSpeakerId", st.get("nextSpeakerId") if st else None)
    _put(s, "pausedReason", session.get("pausedReason"))
    return s


def _is_manual(s: State) -> bool:
    return bool(s["session"]["emotionMode"] == "user")


def _set_display(s: State, character_id: str, emotion: str) -> None:
    if s["displayEmotion"].get(character_id) == emotion:
        return
    s["session"]["participants"] = [
        {**p, "currentEmotion": emotion} if p["characterId"] == character_id else p for p in s["session"]["participants"]
    ]
    s["displayEmotion"][character_id] = emotion


def _clear_pending(s: State, character_id: str) -> None:
    s["pendingEmotion"].pop(character_id, None)


def _put_message(s: State, m: Msg) -> None:
    is_new = m["id"] not in s["messages"]
    if is_new:
        s["order"].append(m["id"])
    s["messages"][m["id"]] = m
    s["session"]["messageCount"] = len(s["order"])
    if is_new:
        _put(s["session"], "lastMessageAt", m.get("createdAt"))


def _next_message_seq(s: State) -> int:
    best = 0
    for mid in s["order"]:
        m = s["messages"].get(mid)
        best = max(best, m["seq"] if m else 0)
    return best + 1


def _patch_state(s: State, patch: dict[str, Any]) -> None:
    st = s["session"].get("state")
    if not st:
        return
    merged = dict(st)
    for k, v in patch.items():
        _put(merged, k, v)
    s["session"]["state"] = merged


def apply_event(state: State, evt: Event) -> State:
    """Apply one event. Pure: returns a new state. Stale events (seq ≤ lastSeq) are ignored."""
    if evt["seq"] <= state["lastSeq"]:
        return state
    s = copy.deepcopy(state)
    _apply(s, evt)
    return s


def reduce_all(initial: State, events: Iterable[Event]) -> State:
    s = copy.deepcopy(initial)
    for evt in events:
        if evt["seq"] > s["lastSeq"]:
            _apply(s, evt)
    return s


def apply_in_place(s: State, events: Iterable[Event]) -> None:
    """Apply events to a state the caller owns (the live EventWriter): no copy of the whole state per event."""
    for evt in events:
        if evt["seq"] > s["lastSeq"]:
            _apply(s, evt)


def ordered_messages(s: State) -> list[Msg]:
    return [s["messages"][mid] for mid in s["order"] if mid in s["messages"]]


def _apply(s: State, evt: Event) -> None:
    prev_thinking = s.get("thinkingId")
    prev_last_at = s.get("lastAt")
    s["lastSeq"] = evt["seq"]
    s["lastAt"] = evt["at"]
    s["session"]["updatedAt"] = evt["at"]
    t = evt["type"]
    p: dict[str, Any] = copy.deepcopy(evt["payload"])
    at: str = evt["at"]

    if t == "turn.next":
        s["nextSpeakerId"] = p["nextSpeakerId"]
        _put(s, "lastSkipped", p.get("skipped"))
        _patch_state(s, {"nextSpeakerId": p["nextSpeakerId"]})
        return

    if t == "turn.thinking":
        s["thinkingId"] = p["characterId"]
        return

    if t == "turn.start":
        message_id: str = p["messageId"]
        author: dict[str, Any] = p["author"]
        variant_id = p.get("variantId")
        existing = s["messages"].get(message_id)
        if existing is not None and variant_id:
            # Regenerate: the original becomes variant 1, the new one streams as the active variant.
            if existing.get("variants"):
                variants = list(existing["variants"])
            else:
                first: dict[str, Any] = {"id": existing.get("activeVariantId") or f"{message_id}_v1",
                                         "content": existing["content"]}
                _put(first, "emotion", existing.get("emotion"))
                first["createdAt"] = existing["createdAt"]
                variants = [first]
            m = dict(existing)
            m["variants"] = [*variants, {"id": variant_id, "content": "", "createdAt": at}]
            m["activeVariantId"] = variant_id
            m["content"] = ""
            m["status"] = "streaming"
            for k in ("interruptedBy", "usage", "trace", "error"):
                m.pop(k, None)
            s["messages"][message_id] = m
        elif existing is None:
            extra: dict[str, Any] = p.get("message") or {}
            m = {"kind": "chat", **extra}
            m["id"] = message_id
            m["sessionId"] = s["session"]["id"]
            m["seq"] = extra["seq"] if extra.get("seq") is not None else _next_message_seq(s)
            m["author"] = author
            m["content"] = ""
            m["status"] = "streaming"
            m["createdAt"] = at
            _put_message(s, m)
        s["streamingId"] = message_id
        s.pop("thinkingId", None)
        turn: dict[str, Any] = {"messageId": message_id}
        _put(turn, "characterId", author.get("characterId"))
        turn["startAt"] = at
        _put(turn, "thinkingAt", prev_last_at if prev_thinking else None)
        s["turn"] = turn
        emotion = p.get("emotion")
        if emotion and author.get("characterId"):
            _apply_emotion(s, message_id, author["characterId"], emotion, "llm", at)
        return

    if t == "token":
        message_id = p["messageId"]
        msg = s["messages"].get(message_id)
        if msg is None:
            return
        cur_turn = s.get("turn")
        is_first = cur_turn is not None and not cur_turn.get("firstTokenAt") and cur_turn.get("messageId") == message_id
        delta: str = p["delta"]
        variant_id = p.get("variantId")
        m = dict(msg)
        m["content"] = msg["content"] + delta
        if variant_id and msg.get("variants"):
            m["variants"] = [{**v, "content": v["content"] + delta} if v["id"] == variant_id else v for v in msg["variants"]]
        s["messages"][message_id] = m
        if is_first and s.get("turn"):
            s["turn"] = {**s["turn"], "firstTokenAt": at}
            cid = msg["author"].get("characterId")
            if cid and s["pendingEmotion"].get(cid):
                pe = s["pendingEmotion"][cid]
                _clear_pending(s, cid)
                if not _is_manual(s):
                    _set_display(s, cid, pe)
        return

    if t == "emotion":
        _apply_emotion(s, p.get("messageId"), p["characterId"], p["emotion"], p["source"], at)
        return

    if t == "turn.end":
        message_id = p["messageId"]
        usage = p.get("usage")
        variant_id = p.get("variantId")
        citations = p.get("citations")
        if message_id in s["messages"]:
            m = dict(s["messages"][message_id])
            m["status"] = p["status"]
            _put(m, "interruptedBy", p.get("interruptedBy"))
            _put(m, "usage", usage if usage is not None else m.get("usage"))
            if citations:
                m["citations"] = citations
            elif variant_id:
                m.pop("citations", None)
            s["messages"][message_id] = m
        msg = s["messages"].get(message_id)
        cid = msg["author"].get("characterId") if msg else None
        if cid and s["pendingEmotion"].get(cid):
            pe = s["pendingEmotion"][cid]
            _clear_pending(s, cid)
            if not _is_manual(s):
                _set_display(s, cid, pe)
        streaming = s.get("streamingId")
        known = message_id in s["messages"]
        _put(s, "streamingId", None if streaming == message_id else streaming)
        _put(s, "thinkingId", None if (streaming == message_id or not known) else s.get("thinkingId"))
        if s.get("turn") and s["turn"].get("messageId") == message_id:
            s["turn"] = {**s["turn"], "endAt": at}
        s["session"]["costUsd"] = round6(s["session"]["costUsd"] + ((usage or {}).get("costUsd") or 0))
        return

    if t == "energy":
        e: dict[str, Any] = {"current": p["current"], "max": p["max"], "state": p["state"]}
        _put(e, "fullAt", p.get("fullAt"))
        _put(e, "lastSpent", p.get("spent"))
        e["at"] = at
        s["energyById"][p["characterId"]] = e
        return

    if t == "reaction":
        message_id = p["messageId"]
        if message_id in s["messages"]:
            r: dict[str, Any] = {"characterId": p["characterId"], "emotion": p["emotion"]}
            if p.get("p") is not None:
                r["p"] = p["p"]
            r["at"] = at
            m = dict(s["messages"][message_id])
            m["reactions"] = [*(m.get("reactions") or []), r]
            s["messages"][message_id] = m
        if not _is_manual(s):
            _set_display(s, p["characterId"], p["emotion"])
        return

    if t == "insight":
        message_id = p["messageId"]
        if message_id in s["messages"]:
            s["messages"][message_id] = {**s["messages"][message_id], "trace": p["trace"]}
        return

    if t == "phase":
        s["phase"] = {"phase": p["phase"], "round": p["round"], "iteration": p["iteration"]}
        _patch_state(s, {"phase": p["phase"], "round": p["round"], "iteration": p["iteration"]})
        return

    if t == "watch.state":
        s["watch"] = {"status": p["status"], "paceMs": p["paceMs"], "turnsTaken": p["turnsTaken"], "turnLimit": p["turnLimit"]}
        _patch_state(s, {"status": p["status"], "turnsTaken": p["turnsTaken"], "turnLimit": p["turnLimit"]})
        return

    if t == "session.paused":
        s.pop("thinkingId", None)
        s["paused"] = True
        _put(s, "pausedReason", p.get("reason"))
        s["session"]["status"] = "paused"
        _put(s["session"], "pausedReason", p.get("reason"))
        return

    if t == "session.resumed":
        s["paused"] = False
        s.pop("pausedReason", None)
        s["session"]["status"] = "active"
        s["session"].pop("pausedReason", None)
        return

    if t == "budget.warning":
        s["budgetWarning"] = {**p, "at": at}
        return

    if t == "error":
        err: dict[str, Any] = {"code": p["code"], "message": p["message"], "retryable": p["retryable"]}
        _put(err, "messageId", p.get("messageId"))
        err["at"] = at
        err["seq"] = evt["seq"]
        s["errors"] = [*s["errors"], err]
        mid = p.get("messageId")
        if mid and mid in s["messages"]:
            s["messages"][mid] = {**s["messages"][mid],
                                  "error": {"code": p["code"], "message": p["message"], "retryable": p["retryable"]}}
        return

    if t == "message":
        m = p["message"]
        _put_message(s, m)
        cid = m["author"].get("characterId")
        if cid and m.get("emotion") and m["author"]["type"] == "character" and not _is_manual(s):
            _set_display(s, cid, m["emotion"])
        cost = (m.get("usage") or {}).get("costUsd")
        if cost:
            s["session"]["costUsd"] = round6(s["session"]["costUsd"] + cost)
        return

    if t == "session.state":
        session = {**s["session"], **(p.get("settings") or {})}
        status = p.get("status")
        paused_reason = p.get("pausedReason")
        if status:
            session["status"] = status
            _put(session, "pausedReason",
                 (paused_reason if paused_reason is not None else session.get("pausedReason")) if status == "paused" else None)
        elif paused_reason:
            session["pausedReason"] = paused_reason
        st = p.get("state")
        if st:
            session["state"] = st
        participants = p.get("participants")
        if participants:
            session["participants"] = participants
        s["session"] = session
        s["paused"] = session["status"] == "paused"
        _put(s, "pausedReason", session.get("pausedReason"))
        if st and "phase" in st:
            s["phase"] = {"phase": st["phase"], "round": st["round"], "iteration": st["iteration"]}
            _put(s, "nextSpeakerId", st.get("nextSpeakerId") if st.get("nextSpeakerId") is not None else s.get("nextSpeakerId"))
        if st and "turnsTaken" in st:
            s["watch"] = {"status": st["status"], "paceMs": (s.get("watch") or {}).get("paceMs", 0),
                          "turnsTaken": st["turnsTaken"], "turnLimit": st["turnLimit"]}
        if participants:
            for part in participants:
                s["displayEmotion"][part["characterId"]] = part["currentEmotion"]
        return


def _apply_emotion(s: State, message_id: str | None, character_id: str, emotion: str, source: str, at: str) -> None:
    if not message_id:
        # MANUAL face change (D-51): no message, source "user".
        _clear_pending(s, character_id)
        _set_display(s, character_id, emotion)
        return
    if message_id in s["messages"]:
        m = dict(s["messages"][message_id])
        m["emotion"] = emotion
        m["emotionSource"] = source
        if m.get("activeVariantId") and m.get("variants"):
            m["variants"] = [{**v, "emotion": emotion} if v["id"] == m["activeVariantId"] else v for v in m["variants"]]
        s["messages"][message_id] = m
    turn = s.get("turn")
    if turn and turn.get("messageId") == message_id:
        s["turn"] = {**turn, "emotionAt": turn.get("emotionAt") or at}
    if _is_manual(s):
        return  # recorded for Insight, not displayed (CHAT-04 AC5)
    m2 = s["messages"].get(message_id)
    turn = s.get("turn")
    before_first_token = (
        m2 is not None and m2["status"] == "streaming" and m2["content"] == "" and turn is not None
        and turn.get("messageId") == message_id and not turn.get("firstTokenAt")
    )
    if before_first_token:
        s["pendingEmotion"][character_id] = emotion  # shown at the first token, not before
        return
    _set_display(s, character_id, emotion)
