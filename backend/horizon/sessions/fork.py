"""Fork a session at a playhead (session-lifecycle "Fork a recording", session-event-sourcing "Fork is identical in
both languages", design D8): an exact port of `frontend/src/engine/fork.ts` `forkEvents`.

1. Cut the events at `atSeq`; if a turn was streaming there, extend the cut to that turn's `turn.end`.
2. Rename the session id, then message ids to `msg_<sid>m<i>` in reducer order, event ids to `evt_<sid>e<i>`, and
   renumber `seq` from 1.
3. Re-reduce from the replay base (title ` · live`, `continuedFrom`, `isSeed: false`).
"""

from __future__ import annotations

import copy
import json
from typing import Any

from horizon.services.runtime.reducer import initial_runtime, ordered_messages, reduce_all

Wire = dict[str, Any]


def replay_base(s: Wire) -> Wire:
    """`engine/replay.ts` `replayBase`: the session a recording replays from (state and config kept)."""
    out = copy.deepcopy(s)
    out.update(status="active", costUsd=0, messageCount=0, updatedAt=s["createdAt"])
    out.pop("pausedReason", None)
    out.pop("lastMessageAt", None)
    return out


def fork_events(events: list[Wire], source: Wire, at_seq: int | None, new_id: str, now: str) -> tuple[list[Wire], Wire]:
    """Returns the renamed, renumbered events and the reduced state of the new session."""
    sid = source["id"]
    if at_seq is not None:
        cut = [e for e in events if e["seq"] <= at_seq]
        partial = reduce_all(initial_runtime(replay_base(source)), cut)
        streaming = partial.get("streamingId")
        if streaming:
            end = next((e for e in events if e["seq"] > at_seq and e["type"] == "turn.end"
                        and e["payload"].get("messageId") == streaming), None)
            if end is not None:
                cut = [e for e in events if e["seq"] <= end["seq"]]
        events = cut
    text = json.dumps(events, ensure_ascii=False).replace(f'"{sid}"', f'"{new_id}"')
    reduced = reduce_all(initial_runtime(replay_base(source)), events)
    msg_prefix = new_id.replace("ses_", "msg_", 1)
    for i, mid in enumerate(reduced["order"]):
        text = text.replace(f'"{mid}"', f'"{msg_prefix}m{i}"')
    evt_prefix = new_id.replace("ses_", "evt_", 1)
    re_events = [{**e, "id": f"{evt_prefix}e{i + 1}", "seq": i + 1} for i, e in enumerate(json.loads(text))]
    base = {**replay_base(source), "id": new_id, "title": f"{source['title']} · live", "titleIsCustom": False,
            "isSeed": False, "continuedFrom": sid, "createdAt": now, "updatedAt": now}
    final = reduce_all(initial_runtime(base), re_events)
    return re_events, final


def fork_result(events: list[Wire], source: Wire, at_seq: int | None, new_id: str, now: str) -> Wire:
    """The fixture shape: `{ events, session, messages }`."""
    re_events, final = fork_events(events, source, at_seq, new_id, now)
    return {"events": re_events, "session": final["session"], "messages": ordered_messages(final)}
