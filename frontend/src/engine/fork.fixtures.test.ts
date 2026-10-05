// Shared fork fixtures (backend/tests/fixtures/fork/*.json, session-event-sourcing "Fork is identical in both
// languages"): forkEvents and the backend's sessions/fork.py must give exactly these events, session and messages.
// Regenerate with `npm run fixtures:build`; `npm run fixtures:check` fails when they drift. Owner: SWE.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import type { Message, Session, SessionEvent } from "../contract/types";
import { forkEvents } from "./fork";

interface ForkCase {
  name: string; source: string; atSeq: number | null; newSessionId: string; now: string;
  expected: { events: SessionEvent[]; session: Session; messages: Message[] };
}
const DIR = path.resolve(__dirname, "../../../backend/tests/fixtures/fork");
const SEED = path.resolve(__dirname, "../../../seed/sessions");
const cases = readdirSync(DIR).filter((f) => f.endsWith(".json")).sort()
  .map((f) => JSON.parse(readFileSync(path.join(DIR, f), "utf8")) as ForkCase);
const data = <T>(file: string): T => (JSON.parse(readFileSync(file, "utf8")) as { data: T }).data;
const plain = <T>(x: T): T => JSON.parse(JSON.stringify(x)) as T;

describe("fork fixtures (shared with the backend)", () => {
  it("found the cases, including a mid-stream cut", () => {
    expect(cases.length).toBeGreaterThanOrEqual(4);
    expect(cases.some((c) => c.name.includes("mid_stream"))).toBe(true);
  });
  for (const c of cases) {
    it(c.name, () => {
      const session = data<Session>(path.join(SEED, c.source, "session.json"));
      const events = data<SessionEvent[]>(path.join(SEED, c.source, "events.json"));
      const r = forkEvents(events, session, c.atSeq ?? undefined, c.newSessionId, c.now);
      expect(plain(r.events)).toEqual(c.expected.events);
      expect(plain(r.session)).toEqual(c.expected.session);
      expect(plain(r.messages)).toEqual(c.expected.messages);
      expect(r.messages.every((m) => m.status !== "streaming")).toBe(true);
    });
  }
});
