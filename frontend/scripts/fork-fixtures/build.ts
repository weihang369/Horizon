// Cross-language fixtures shared with the backend (session-runtime design D8; generation-jobs design D2, D9):
//   backend/tests/fixtures/fork/*.json        forkEvents() over seed recordings at several playheads (one mid-stream)
//   backend/tests/fixtures/export/*.json      the MockClient's Markdown export of seed sessions, byte for byte
//   backend/tests/fixtures/job_plans/*.json   planTasks()/estimateJob() for every job kind × generation mode
//   backend/tests/fixtures/drafts/*.json      draftFromSeed() for seed lines × intents, and regenerateField() cases
//   backend/tests/fixtures/theme_spec/*.json  themeSpecFromBrief() for every seed brief and a few edited briefs
// Both languages assert these files. Deterministic: a fixed new session ID and a fixed "now".
//   npm run fixtures:build   regenerate and write
//   npm run fixtures:check   regenerate in memory and fail on any difference
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { CharacterProfile, Session, SessionEvent, SongBrief, ThemeSong } from "../../src/contract/types";
import type { StartJobInput } from "../../src/client/HorizonClient";
import { themeSpecFromBrief } from "../../src/audio/synth/spec";
import { forkEvents } from "../../src/engine/fork";
import { draftFromSeed, regenerateField } from "../../src/mock/banks/drafts";
import { datasetFromFiles } from "../../src/mock/db/dataset";
import { estimateJob, planTasks } from "../../src/mock/engines/jobs";
import type { JobHost } from "../../src/mock/engines/jobs";
import { MockClient } from "../../src/mock/MockClient";
import { DEFAULT_TIMING } from "../../src/mock/timing.config";

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
  for (const [rel, content] of jobPlanFixtures(seedDir)) out.set(rel, content);
  for (const [rel, content] of draftFixtures()) out.set(rel, content);
  for (const [rel, content] of themeSpecFixtures(seedDir)) out.set(rel, content);
  return out;
}

const json = (v: unknown) => `${JSON.stringify(v, null, 1)}\n`;

/** planTasks()/estimateJob() per job kind and generation mode (the backend's `plans.py` port asserts these). */
function jobPlanFixtures(seedDir: string): Map<string, string> {
  const out = new Map<string, string>();
  const settings = readSeed(seedDir, "settings.json") as { models: Record<string, string> };
  const pricing = readSeed(seedDir, "pricing.json") as JobHost["pricing"];
  const host = (mode: "lean" | "standard") => ({
    db: { settings: { ...settings, generationMode: mode } }, timing: DEFAULT_TIMING, pricing,
  }) as unknown as JobHost;
  const inputs: { name: string; input: StartJobInput }[] = [
    { name: "profile_draft", input: { characterId: "chr_x", kind: "profile_draft" } },
    { name: "profile_regenerate", input: { characterId: "chr_x", kind: "profile_regenerate", targetField: "tagline" } },
    { name: "portrait_candidates", input: { characterId: "chr_x", kind: "portrait_candidates" } },
    { name: "portrait_tweak", input: { characterId: "chr_x", kind: "portrait_tweak", prompt: "warmer smile" } },
    { name: "emotion_set", input: { characterId: "chr_x", kind: "emotion_set" } },
    { name: "emotion_set_sheet", input: { characterId: "chr_x", kind: "emotion_set", technique: "expression_sheet" } },
    { name: "emotion_set_listed", input: { characterId: "chr_x", kind: "emotion_set", emotions: ["thinking", "happy"] } },
    { name: "emotion_regenerate", input: { characterId: "chr_x", kind: "emotion_regenerate" } },
    { name: "emotion_regenerate_two", input: { characterId: "chr_x", kind: "emotion_regenerate", emotions: ["sad", "angry"] } },
    { name: "song", input: { characterId: "chr_x", kind: "song" } },
  ];
  for (const mode of ["lean", "standard"] as const) {
    for (const { name, input } of inputs) {
      let n = 0;
      const { plans, parallel } = planTasks(host(mode), input, () => `task_${n++}`);
      out.set(`job_plans/${name}_${mode}.json`, json({
        input, mode, parallel, estimatedCostUsd: estimateJob(host(mode), input),
        tasks: plans.map((p) => ({ type: p.task.type, ...(p.task.emotion ? { emotion: p.task.emotion } : {}), ms: p.ms, cost: p.cost, category: p.category })),
      }));
    }
  }
  return out;
}

/** The scripted drafter's bank (the backend's `drafts.py` port asserts these, byte for byte). */
function draftFixtures(): Map<string, string> {
  const out = new Map<string, string>();
  const seeds = [
    "Sarah, a doctor", "Noor, a baker", "a retired train engineer who loves fishing", "Kenji the barista",
    "an economist", "Marcus, an attorney who argues about everything", "lowercase start, a nurse", "Élodie, une artiste peintre",
  ];
  const intents = ["expert", "companion", "other"] as const;
  seeds.forEach((seed, i) => {
    const cases = intents.map((intent) => ({ seed, intent, draft: draftFromSeed(seed, intent) }));
    out.set(`drafts/seed_${i + 1}.json`, json({ seed, cases }));
  });
  const base = draftFromSeed("Sarah, a doctor", "expert").profile as CharacterProfile;
  const fields = ["tagline", "greeting", "backstory", "goals", "role", "unknownField"];
  const regen = fields.flatMap((field) => [1, 2, 7].map((attempt) => ({ field, attempt, patch: regenerateField(base, field, attempt) })));
  out.set("drafts/regenerate_field.json", json({ profile: base, cases: regen }));
  return out;
}

/** themeSpecFromBrief() for the shipped briefs and a few edits (the backend's `theme.py` port asserts these). */
function themeSpecFixtures(seedDir: string): Map<string, string> {
  const out = new Map<string, string>();
  const songs = readdirSync(path.join(seedDir, "songs")).filter((f) => f.endsWith(".json")).sort()
    .map((f) => readSeed(seedDir, `songs/${f}`) as ThemeSong);
  const edited: { seed: string; title?: string; brief: SongBrief }[] = [
    { seed: "chr_editA", title: "Ada's Theme", brief: { genres: ["city-pop"], moods: ["playful"], bpm: 112, instruments: ["piano", "bells"], vibe: "late shift, neon puddles" } },
    { seed: "chr_editB", brief: { genres: ["piano"], moods: ["calm"], bpm: 72, instruments: ["piano"], vibe: "rain on the window" } },
    { seed: "chr_editC", title: "Ünal’s Theme", brief: { genres: ["synthwave", "lo-fi"], moods: ["confident", "hopeful"], bpm: 124, instruments: ["synth", "guitar"], vibe: "a road trip at dawn" } },
  ];
  const cases = [
    ...songs.map((s) => ({ seed: s.characterId, title: `${s.characterId}'s Theme`, brief: s.brief })),
    ...edited,
  ].map((c) => ({ ...c, spec: themeSpecFromBrief(c.seed, c.brief, c.title) }));
  out.set("theme_spec/cases.json", json({ cases }));
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
