// Shared creation fixtures (generation-jobs design D2, D9): the backend's plans.py, drafts.py and theme.py ports must give
// exactly these. Regenerate with `npm run fixtures:build`; `npm run fixtures:check` fails when they drift. Owner: SWE.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import type { CharacterProfile, SongBrief } from "../contract/types";
import type { StartJobInput } from "../client/HorizonClient";
import { themeSpecFromBrief } from "../audio/synth/spec";
import { draftFromSeed, regenerateField } from "./banks/drafts";
import { estimateJob, planTasks } from "./engines/jobs";
import type { JobHost } from "./engines/jobs";
import { DEFAULT_TIMING } from "./timing.config";

const FIX = path.resolve(__dirname, "../../../backend/tests/fixtures");
const SEED = path.resolve(__dirname, "../../../seed");
const read = <T>(rel: string): T => JSON.parse(readFileSync(path.join(FIX, rel), "utf8")) as T;
const seed = <T>(rel: string): T => (JSON.parse(readFileSync(path.join(SEED, rel), "utf8")) as { data: T }).data;
const plain = <T>(x: T): T => JSON.parse(JSON.stringify(x)) as T;

interface PlanFixture {
  input: StartJobInput; mode: "lean" | "standard"; parallel: number; estimatedCostUsd: number;
  tasks: { type: string; emotion?: string; ms: number; cost: number; category: string }[];
}

describe("job plan fixtures (shared with the backend)", () => {
  const files = readdirSync(path.join(FIX, "job_plans")).filter((f) => f.endsWith(".json")).sort();
  it("covers every job kind in both modes", () => {
    const kinds = new Set(files.map((f) => read<PlanFixture>(`job_plans/${f}`).input.kind));
    expect([...kinds].sort()).toEqual(["emotion_regenerate", "emotion_set", "portrait_candidates", "portrait_tweak",
      "profile_draft", "profile_regenerate", "song"]);
    expect(files.length).toBe(20);
  });
  for (const f of files) {
    it(f, () => {
      const fx = read<PlanFixture>(`job_plans/${f}`);
      const host = { db: { settings: { ...seed<object>("settings.json"), generationMode: fx.mode } }, timing: DEFAULT_TIMING,
        pricing: seed<JobHost["pricing"]>("pricing.json") } as unknown as JobHost;
      let n = 0;
      const { plans, parallel } = planTasks(host, fx.input, () => `task_${n++}`);
      expect(parallel).toBe(fx.parallel);
      expect(estimateJob(host, fx.input)).toBe(fx.estimatedCostUsd);
      expect(plans.map((p) => ({ type: p.task.type, ...(p.task.emotion ? { emotion: p.task.emotion } : {}), ms: p.ms, cost: p.cost, category: p.category })))
        .toEqual(fx.tasks);
    });
  }
});

describe("draft bank fixtures (shared with the backend)", () => {
  const files = readdirSync(path.join(FIX, "drafts")).filter((f) => f.startsWith("seed_")).sort();
  it("found the seed lines", () => expect(files.length).toBeGreaterThanOrEqual(6));
  for (const f of files) {
    it(f, () => {
      const fx = read<{ cases: { seed: string; intent: "expert" | "companion" | "other"; draft: unknown }[] }>(`drafts/${f}`);
      for (const c of fx.cases) expect(plain(draftFromSeed(c.seed, c.intent))).toEqual(c.draft);
    });
  }
  it("regenerate_field.json", () => {
    const fx = read<{ profile: CharacterProfile; cases: { field: string; attempt: number; patch: unknown }[] }>("drafts/regenerate_field.json");
    for (const c of fx.cases) expect(plain(regenerateField(fx.profile, c.field, c.attempt))).toEqual(c.patch);
  });
});

describe("theme spec fixtures (shared with the backend)", () => {
  it("cases.json", () => {
    const fx = read<{ cases: { seed: string; title?: string; brief: SongBrief; spec: unknown }[] }>("theme_spec/cases.json");
    expect(fx.cases.length).toBeGreaterThanOrEqual(9);
    for (const c of fx.cases) expect(plain(themeSpecFromBrief(c.seed, c.brief, c.title))).toEqual(c.spec);
  });
});
