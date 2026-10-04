// Cross-language fixtures for the backend's session runtime (session-runtime design D8, task 11.1/11.5):
//   backend/tests/fixtures/fork/*.json      forkEvents() over seed recordings at several playheads (one mid-stream)
//   backend/tests/fixtures/export/*.json    the MockClient's Markdown export of seed sessions, byte for byte
// Both languages assert these files. Deterministic: a fixed new session ID and a fixed "now".
//   npm run fixtures:build   regenerate and write
//   npm run fixtures:check   regenerate in memory and fail on any difference
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { Session, SessionEvent } from "../../src/contract/types";
import { forkEvents } from "../../src/engine/fork";
import { datasetFromFiles } from "../../src/mock/db/dataset";
import { MockClient } from "../../src/mock/MockClient";

const NEW_ID = "ses_forkFixture1";
const NOW = "2026-10-03T03:00:00.000Z";

interface ForkCase { name: string; doc: string; source: string; atSeq: number | null }

function readSeed(seedDir: string, rel: string): unknown {
  const doc = JSON.parse(readFileSync(path.join(seedDir, rel), "utf8")) as { data: unknown };
  return doc.data;
}

function seedFiles(seedDir: string, rel = ""): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  const dir = path.join(seedDir, rel);
  for (const name of readdirSync(dir, { withFileTypes: true })) {
    const r = rel ? `${rel}/${name.name}` : name.name;
    if (name.isDirectory()) {
      if (r === "assets") continue;
      Object.assign(out, seedFiles(seedDir, r));
    } else if (r.endsWith(".json")) {
      out[`seed/${r}`] = JSON.parse(readFileSync(path.join(seedDir, r), "utf8"));
    }
  }
  return out;
}

function midStreamSeq(events: SessionEvent[], after: number): number {
  const start = events.find((e) => e.seq > after && e.type === "turn.start");
  if (!start) throw new Error("no turn.start to cut inside");
  const token = events.find((e) => e.seq > start.seq && e.type === "token");
  if (!token) throw new Error("no token after turn.start");
  return token.seq;
}

export async function buildFixtures(seedDir: string): Promise<Map<string, string>> {
  const out = new Map<string, string>();
  const load = (sid: string) => ({
    session: readSeed(seedDir, `sessions/${sid}/session.json`) as Session,
    events: readSeed(seedDir, `sessions/${sid}/events.json`) as SessionEvent[],
  });
  const debate = load("ses_seedDebate4Day");
  const cases: ForkCase[] = [
    { name: "debate_third", doc: "The portable test's playhead: a third of the way through the seed debate.", source: "ses_seedDebate4Day",
      atSeq: debate.events[Math.floor(debate.events.length / 3)].seq },
    { name: "debate_mid_stream", doc: "A playhead inside a streaming reply: the cut extends to that turn's turn.end.", source: "ses_seedDebate4Day",
      atSeq: midStreamSeq(debate.events, Math.floor(debate.events.length / 2)) },
    { name: "amara_full", doc: "No playhead: the whole recording.", source: "ses_seedAmaraHeadache", atSeq: null },
    { name: "hana_early", doc: "An early playhead in a 1:1 recording.", source: "ses_seedHanaLongDay", atSeq: 5 },
    { name: "dinner_mid_stream", doc: "A group recording cut inside a reply.", source: "ses_seedDinner",
      atSeq: midStreamSeq(load("ses_seedDinner").events, 3) },
  ];
  for (const c of cases) {
    const src = load(c.source);
    const r = forkEvents(src.events, src.session, c.atSeq ?? undefined, NEW_ID, NOW);
    const fixture = { name: c.name, doc: c.doc, source: c.source, atSeq: c.atSeq, newSessionId: NEW_ID, now: NOW,
      expected: { events: r.events, session: r.session, messages: r.messages } };
    out.set(`fork/${c.name}.json`, `${JSON.stringify(fixture, null, 1)}\n`);
  }
  // The MockClient's own export (not a re-implementation), on the shipped seed only.
  const client = new MockClient({ dataset: datasetFromFiles(seedFiles(seedDir), { includeMock: false }), storage: null });
  await client.ready;
  for (const sid of ["ses_seedDebate4Day", "ses_seedAmaraHeadache"]) {
    const markdown = await client.sessions.export(sid);
    out.set(`export/${sid}.json`, `${JSON.stringify({ sessionId: sid, markdown }, null, 1)}\n`);
  }
  return out;
}

export async function main(mode: "build" | "check", seedDir: string, outDir: string): Promise<number> {
  const files = await buildFixtures(seedDir);
  const problems: string[] = [];
  for (const [rel, content] of files) {
    const file = path.join(outDir, rel);
    const same = existsSync(file) && readFileSync(file, "utf8").replace(/\r\n/g, "\n") === content;
    if (mode === "check") {
      if (!same) problems.push(rel);
      continue;
    }
    if (!same) {
      mkdirSync(path.dirname(file), { recursive: true });
      writeFileSync(file, content);
    }
  }
  if (problems.length) {
    console.error(`[fixtures:check] out of date: ${problems.join(", ")}. Run: npm run fixtures:build`);
    return 1;
  }
  console.log(`[fixtures:${mode}] ${files.size} files ${mode === "check" ? "match" : "written"} → ${outDir}`);
  return 0;
}
