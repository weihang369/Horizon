// A resumed or retried job keeps the plans it started with (audit F-04): the same time, price, category and model
// per task, and the input fields `apply` reads (a field regenerate's target, the expression sheet).
import { describe, expect, it } from "vitest";
import type { StartJobInput } from "../../client/HorizonClient";
import type { Character, GenerationJob } from "../../contract/types";
import type { Dataset } from "../db/dataset";
import { PRICING, MODELS } from "../pricing.config";
import type { Scheduler } from "../time/Scheduler";
import { DEFAULT_TIMING } from "../timing.config";
import { JobRunner, planTasks, replan, type JobHost } from "./jobs";

const CID = "chr_t";

function host(): JobHost {
  const db = {
    settings: { models: { image: MODELS.image, music: MODELS.music, chat: MODELS.chat }, generationMode: "full" },
    characters: { [CID]: { id: CID, status: "draft", appearance: { candidates: [] } } as unknown as Character },
    jobs: {}, ledger: [],
  } as unknown as Dataset;
  return {
    db, timing: DEFAULT_TIMING, pricing: PRICING, sched: { every: () => () => {} } as unknown as Scheduler,
    newId: (p) => `${p}_1`, iso: () => "2026-10-27T00:00:00Z", jobFault: () => undefined,
    emitJob: () => {}, ledger: () => {}, changed: () => {},
  };
}

function started(h: JobHost, input: StartJobInput) {
  let n = 0;
  const { plans, parallel } = planTasks(h, input, () => `task_${n++}`);
  const job = { id: "job_t", characterId: CID, kind: input.kind, ...(input.targetField ? { targetField: input.targetField } : {}),
    tasks: plans.map((p) => p.task) } as unknown as GenerationJob;
  return { job, plans, parallel };
}

const INPUTS: StartJobInput[] = [
  { characterId: CID, kind: "profile_draft" },
  { characterId: CID, kind: "profile_regenerate", targetField: "tagline" },
  { characterId: CID, kind: "portrait_candidates" },
  { characterId: CID, kind: "portrait_tweak", prompt: "x" },
  { characterId: CID, kind: "emotion_set" },
  { characterId: CID, kind: "emotion_set", technique: "expression_sheet" },
  { characterId: CID, kind: "emotion_regenerate", emotions: ["sad"] },
  { characterId: CID, kind: "song" },
];

describe("replan (mock jobs)", () => {
  it.each(INPUTS.map((i) => [`${i.kind}${i.technique ? ` (${i.technique})` : ""}`, i] as const))(
    "%s: the same plan as at the start", (_name, input) => {
      const h = host();
      const { job, plans, parallel } = started(h, input);
      const again = replan(h, job);
      expect(again.parallel).toBe(parallel);
      for (const p of plans) {
        const q = again.plans.get(p.task.id)!;
        expect({ ms: q.ms, cost: q.cost, category: q.category, model: q.model })
          .toEqual({ ms: p.ms, cost: p.cost, category: p.category, model: p.model });
      }
      expect(again.input.targetField).toBe(input.targetField);
      expect(again.input.technique === "expression_sheet").toBe(input.technique === "expression_sheet");
    });

  it("retrying a failed expression sheet brings back the emotions it skipped", () => {
    const h = host();
    const { job } = started(h, { characterId: CID, kind: "emotion_set", technique: "expression_sheet" });
    const sheet = job.tasks.find((t) => t.type === "expression_sheet")!;
    Object.assign(sheet, { status: "failed", attempt: 1 });
    for (const t of job.tasks) if (t !== sheet) t.status = "skipped";
    h.db.jobs[job.id] = job;
    new JobRunner(h).retryTask(job.id, sheet.id);
    expect(sheet.status).toBe("running");
    expect(job.tasks.filter((t) => t.type === "emotion_image").every((t) => t.status === "queued")).toBe(true);
  });
});
