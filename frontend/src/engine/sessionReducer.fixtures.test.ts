// Shared reducer fixtures (backend/tests/fixtures/reducer/*.json): the TS reducer and the Python port (M1b, D-79)
// must derive the same session and messages from the same events.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import type { Message, Session, SessionEvent } from "../contract/types";
import { SessionEventSchema } from "../contract/schemas";
import { initialRuntime, orderedMessages, reduceAll } from "./sessionReducer";

interface ReducerCase {
  name: string; session: Session; events: SessionEvent[];
  expected: { session: Session; messages: Message[] };
}
const DIR = path.resolve(__dirname, "../../../backend/tests/fixtures/reducer");
const cases = readdirSync(DIR).filter((f) => f.endsWith(".json")).sort()
  .map((f) => JSON.parse(readFileSync(path.join(DIR, f), "utf8")) as ReducerCase);
// JSON drops undefined; compare in the same form.
const plain = <T>(x: T): T => JSON.parse(JSON.stringify(x)) as T;

describe("reducer fixtures (shared with the backend)", () => {
  it("found the cases", () => {
    expect(cases.length).toBeGreaterThanOrEqual(6);
  });
  for (const c of cases) {
    it(c.name, () => {
      for (const e of c.events) expect(SessionEventSchema.safeParse(e).success, `${c.name} seq ${e.seq}`).toBe(true);
      const s = reduceAll(initialRuntime(c.session), c.events);
      expect(plain(s.session)).toEqual(c.expected.session);
      expect(plain(orderedMessages(s))).toEqual(c.expected.messages);
    });
  }
});
