// Client-surface schemas (rev 1.3): every GlobalEvent / JobEvent variant parses, so the backend's SSE can be validated.
import { describe, expect, it } from "vitest";
import type { GlobalEvent, JobEvent } from "../client/HorizonClient";
import type { GenerationJob, GenerationTask } from "./types";
import { GlobalEventSchema, JobEventSchema } from "./schemas";

const task: GenerationTask = { id: "task_a1", type: "emotion_image", emotion: "happy", status: "running", attempt: 1, maxAttempts: 2 };
const job: GenerationJob = {
  id: "job_a1", characterId: "chr_a1", kind: "emotion_set", status: "running", progress: 0.5,
  estimatedCostUsd: 0.09, actualCostUsd: 0.018, tasks: [task], createdAt: "2026-10-03T03:00:00Z",
};

const GLOBALS: Record<GlobalEvent["type"], GlobalEvent> = {
  "entity.changed": { type: "entity.changed", kind: "knowledge", id: "kno_a1", worldId: "wld_a1", progress: { stage: "chunking", pct: 0.4 } },
  "budget.warning": { type: "budget.warning", scope: "daily", spentUsd: 0.8, capUsd: 1 },
  "budget.reached": { type: "budget.reached", scope: "creation", spentUsd: 0.6, capUsd: 0.6, jobId: "job_a1" },
  "job.progress": { type: "job.progress", job },
  "task.update": { type: "task.update", jobId: "job_a1", task },
  "job.done": { type: "job.done", job: { ...job, status: "succeeded", progress: 1 }, characterName: "Hana" },
  error: { type: "error", error: { code: "conflict", message: "Another session is live.", retryable: false, details: { activeSessionId: "ses_a1" } } },
  "mock.reset": { type: "mock.reset" },
};

describe("client-surface schemas", () => {
  for (const [type, e] of Object.entries(GLOBALS)) {
    it(`GlobalEvent ${type} parses`, () => {
      expect(GlobalEventSchema.safeParse(e).success).toBe(true);
    });
  }

  it("rejects an entity.changed progress with an unknown stage", () => {
    expect(GlobalEventSchema.safeParse({ type: "entity.changed", kind: "knowledge", progress: { stage: "ocr", pct: 0.1 } }).success).toBe(false);
  });

  it("every JobEvent variant parses", () => {
    const events: JobEvent[] = [{ type: "job.progress", job }, { type: "task.update", jobId: job.id, task }, { type: "job.done", job }];
    for (const e of events) expect(JobEventSchema.safeParse(e).success, e.type).toBe(true);
  });
});
