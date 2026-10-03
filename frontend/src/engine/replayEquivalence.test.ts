// Replay equivalence (EE paper §2.10): reducing a recording's events from its replay base reproduces its
// messages.json exactly and its session.json (status, state, participants, cost, counts). Owner: EE.
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

  it("Mei's bar reads 742 right after msg_seedD08 (doc 05 §8 trace.energy.remaining)", () => {
    const events = read<SessionEvent[]>("sessions/ses_seedDebate4Day/events.json");
    const end = events.find((e) => e.type === "turn.end" && (e.payload as { messageId: string }).messageId === "msg_seedD08")!;
    const drain = events.find((e) => e.seq > end.seq && e.type === "energy" && (e.payload as { characterId: string }).characterId === "chr_seedMei")!;
    const at = replayTo(read<Session>("sessions/ses_seedDebate4Day/session.json"), events, drain.seq);
    expect(at.energyById.chr_seedMei).toMatchObject({ current: 742, lastSpent: 5 });
  });
});
