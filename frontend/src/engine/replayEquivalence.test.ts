// Replay equivalence (EE paper §2.10): reducing a recording's events from its replay base reproduces its
// messages.json exactly and its session.json (status, state, participants, cost, counts).
import { readdirSync, readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import type { Message, Session, SessionEvent } from "../contract/types";
import { replayTo } from "./replay";
import { orderedMessages } from "./sessionReducer";
import { timelineFromEvents } from "./ScriptPlayer";

const SEED = path.resolve(__dirname, "../../../seed");
const dirs = ["sessions", "_mock/sessions"].flatMap((d) => (existsSync(path.join(SEED, d)) ? readdirSync(path.join(SEED, d)).map((s) => `${d}/${s}`) : []));
const read = <T,>(rel: string) => (JSON.parse(readFileSync(path.join(SEED, rel), "utf8")) as { data: T }).data;

describe("replay equivalence", () => {
  it("covers every recorded session", () => {
    expect(dirs.length).toBeGreaterThanOrEqual(5);
  });

  for (const dir of dirs) {
    it(dir, () => {
      const session = read<Session>(`${dir}/session.json`);
      const messages = read<Message[]>(`${dir}/messages.json`);
      const events = read<SessionEvent[]>(`${dir}/events.json`);
      const final = replayTo(session, events);
      expect(orderedMessages(final)).toEqual(messages);
      const { updatedAt: _u1, ...got } = final.session;
      const { updatedAt: _u2, ...want } = session;
      expect(got).toEqual(want);
      expect(final.streamingId).toBeUndefined();
    });
  }

  it("Replay pacing comes from the `at` deltas with gaps over 2.5 s trimmed", () => {
    const events = read<SessionEvent[]>("sessions/ses_seedDebate4Day/events.json");
    const trimmed = timelineFromEvents(events);
    const raw = timelineFromEvents(events, { trimGapsMs: null });
    for (let i = 1; i < trimmed.length; i++) expect(trimmed[i].t - trimmed[i - 1].t).toBeLessThanOrEqual(2500);
    expect(raw.at(-1)!.t).toBeGreaterThanOrEqual(trimmed.at(-1)!.t);
  });

  it("a break between visits plays short even with the trim off (U-97)", () => {
    const at = (iso: string, seq: number) => ({ id: `e${seq}`, sessionId: "s", seq, at: iso, type: "session.resumed", payload: {} } as SessionEvent);
    const events = [at("2026-09-27T10:00:00.000Z", 1), at("2026-09-27T10:00:20.000Z", 2), at("2026-10-23T04:00:00.000Z", 3)];
    const raw = timelineFromEvents(events, { trimGapsMs: null });
    expect(raw.map((x) => x.t)).toEqual([0, 20_000, 22_500]);   // the 20 s pause kept, the 26 days as 2.5 s
    expect(timelineFromEvents(events).map((x) => x.t)).toEqual([0, 2500, 5000]);
  });

  it("Mei's bar reads 996 right after msg_seedD08 (doc 05 §8 trace.energy.remaining)", () => {
    const events = read<SessionEvent[]>("sessions/ses_seedDebate4Day/events.json");
    const end = events.find((e) => e.type === "turn.end" && (e.payload as { messageId: string }).messageId === "msg_seedD08")!;
    const drain = events.find((e) => e.seq > end.seq && e.type === "energy" && (e.payload as { characterId: string }).characterId === "chr_seedMei")!;
    const at = replayTo(read<Session>("sessions/ses_seedDebate4Day/session.json"), events, drain.seq);
    expect(at.energyById.chr_seedMei).toMatchObject({ current: 996, lastSpent: 2 });
  });
});
