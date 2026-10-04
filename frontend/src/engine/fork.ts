// Fork a recording at a playhead (R16, D-51; session-runtime design D8). Pure. Owner: EE.
// Extracted from MockClient.fork so the backend's port (backend/horizon/sessions/fork.py) can be pinned to it by the
// shared fixtures in backend/tests/fixtures/fork/: cut the events at `atSeq` (finishing a turn that was streaming
// there), rename the session, message and event IDs deterministically, renumber seq from 1, and re-reduce.
import type { Message, Session, SessionEvent } from "../contract/types";
import { replayBase } from "./replay";
import type { SessionRuntimeState } from "./sessionReducer";
import { initialRuntime, orderedMessages, reduceAll } from "./sessionReducer";

export interface ForkResult {
  events: SessionEvent[];
  state: SessionRuntimeState;
  session: Session;
  messages: Message[];
}

export function forkEvents(sourceEvents: SessionEvent[], source: Session, atSeq: number | undefined, newSessionId: string, now: string): ForkResult {
  const id = source.id;
  let events = sourceEvents;
  if (atSeq !== undefined) {
    let cut = events.filter((e) => e.seq <= atSeq);
    // Finish the turn that was streaming at the playhead.
    const partial = reduceAll(initialRuntime(replayBase(source)), cut);
    if (partial.streamingId) {
      const end = events.find((e) => e.seq > atSeq && e.type === "turn.end" && (e.payload as { messageId: string }).messageId === partial.streamingId);
      if (end) cut = events.filter((e) => e.seq <= end.seq);
    }
    events = cut;
  }
  const sid = newSessionId;
  let json = JSON.stringify(events).split(`"${id}"`).join(`"${sid}"`);
  const reduced = reduceAll(initialRuntime(replayBase(source)), events);
  reduced.order.forEach((mid, i) => { json = json.split(`"${mid}"`).join(`"${sid.replace("ses_", "msg_")}m${i}"`); });
  const reEvents = (JSON.parse(json) as SessionEvent[]).map((e, i) => ({ ...e, id: `${sid.replace("ses_", "evt_")}e${i + 1}`, seq: i + 1 }));
  const base: Session = {
    ...replayBase(source), id: sid, title: `${source.title} · live`, titleIsCustom: false, isSeed: false, continuedFrom: id, createdAt: now, updatedAt: now,
  };
  const final = reduceAll(initialRuntime(base), reEvents);
  return { events: reEvents, state: final, session: final.session, messages: orderedMessages(final) };
}
