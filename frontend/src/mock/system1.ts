// The MockClient's System 1 rows (docs/ai/13 W1; system1-trace "Route rows"). The fixed row fields come from the
// shared fixture that seed-build generates from the backend's question bank, so the mock and the scripted backend
// show the same rows; the answer is filled from what actually happened. Seed recordings never get rows (W1).
import fixture from "@seed/system1.fixture.json";
import type { System1Row, TurnSystem1 } from "../contract/types";

type FixtureRow = Omit<System1Row, "answer" | "about">;
const ROWS = (fixture as unknown as { data: { rows: Record<string, FixtureRow> } }).data.rows;

/** A fixture row with its answer (and `about`) filled in. */
export function fixtureRow(id: string, answer: string, about?: string): System1Row {
  const r = ROWS[id];
  if (!r) throw new Error(`no System 1 fixture row for ${id}`);
  return { ...r, compared: r.compared?.map((c) => ({ ...c })), answer, ...(about ? { about } : {}) };
}

/** The `route` row a group reply carries: the router's top pick, shared by every reply that decision started. */
export function routeSystem1(topPick: string): TurnSystem1 {
  return { questions: [fixtureRow("route", topPick)] };
}
