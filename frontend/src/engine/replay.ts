// Replay helpers (MULTI-15, R1). Pure. Owner: EE.
// A recording replays from its session's starting point: the first event (session.state) restores status, state
// and participants; costs and counts are rebuilt by the reducer from the events.
import type { Session, SessionEvent } from "../contract/types";
import type { SessionRuntimeState } from "./sessionReducer";
import { initialRuntime, reduceAll } from "./sessionReducer";

export function replayBase(s: Session): Session {
  return { ...s, status: "active", pausedReason: undefined, costUsd: 0, messageCount: 0, lastMessageAt: undefined, updatedAt: s.createdAt };
}

/** Initial runtime for replaying `session` (no messages yet). */
export const replayInitial = (session: Session): SessionRuntimeState => initialRuntime(replayBase(session));

/** State after the events with seq ≤ atSeq (or all). */
export function replayTo(session: Session, events: SessionEvent[], atSeq = Infinity): SessionRuntimeState {
  return reduceAll(replayInitial(session), events.filter((e) => e.seq <= atSeq));
}
