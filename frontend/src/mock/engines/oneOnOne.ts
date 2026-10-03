// 1:1 engine (CHAT-01..06, ENG-04). Owner: EE.
import { greetingFor } from "../banks";
import type { EngineHost } from "./host";
import { asleepNote, enqueue, isAsleep, speakThen, userMessage } from "./host";

export function greet(h: EngineHost, sid: string): void {
  const live = h.live(sid);
  const cid = live.state.session.participants[0]?.characterId;
  const c = cid ? h.db.characters[cid] : undefined;
  if (!c || !cid) return;
  enqueue(live, (done) => h.after(sid, h.timing.greetingMs, () => {
    if (isAsleep(h, cid)) {
      asleepNote(h, sid, cid, false);
      done();
      return;
    }
    speakThen(h, sid, cid, { line: greetingFor(c) }, () => done());
  }));
}

export function send(h: EngineHost, sid: string, text: string): void {
  const live = h.live(sid);
  const cid = live.state.session.participants[0]?.characterId;
  h.emit(sid, { type: "message", payload: { message: userMessage(h, sid, text) } });
  if (!cid) return;
  enqueue(live, (done) => {
    if (isAsleep(h, cid)) {
      asleepNote(h, sid, cid, false);
      done();
      return;
    }
    speakThen(h, sid, cid, { prompt: text }, () => done());
  });
}

export function regenerate(h: EngineHost, sid: string, messageId: string): void {
  const live = h.live(sid);
  const m = live.state.messages[messageId];
  const cid = m?.author.characterId;
  if (!m || !cid) return;
  const prompt = [...live.state.order].reverse().map((id) => live.state.messages[id]).find((x) => x?.author.type === "user" && x.seq < m.seq)?.content ?? "";
  enqueue(live, (done) => {
    if (isAsleep(h, cid)) {
      asleepNote(h, sid, cid, false);
      done();
      return;
    }
    speakThen(h, sid, cid, { prompt: `${prompt} (again)`, variantOf: messageId }, () => done());
  });
}
