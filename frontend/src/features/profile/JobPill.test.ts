import { describe, expect, it } from "vitest";
import type { GenerationJob, GenerationTask } from "@/contract/types";
import { jobLabel, pillState } from "./JobPill";

const task = (status: GenerationTask["status"], type: GenerationTask["type"] = "emotion_image") => ({ id: Math.random().toString(36), type, status }) as GenerationTask;
const job = (status: GenerationJob["status"], tasks: GenerationTask[] = [], kind: GenerationJob["kind"] = "emotion_set"): GenerationJob => ({
  id: "job_1", characterId: "chr_x", kind, status, progress: 0.4, estimatedCostUsd: 0.1, actualCostUsd: 0, tasks, createdAt: "2026-10-03T00:00:00Z",
});

describe("job pill state", () => {
  it("runs, warns on a failed task mid-run, and reports the outcome", () => {
    expect(pillState(job("running", [task("running")]))).toBe("run");
    expect(pillState(job("running", [task("failed"), task("running")]))).toBe("warn");
    expect(pillState(job("succeeded"))).toBe("done");
    expect(pillState(job("partial"))).toBe("warn");
    expect(pillState(job("failed"))).toBe("fail");
    expect(pillState(job("cancelled"))).toBe("fail");
  });
  it("labels counted tasks while running and the outcome after", () => {
    expect(jobLabel(job("running", [task("succeeded"), task("running"), task("queued")]))).toBe("Emotions 1/3");
    expect(jobLabel(job("running", [], "song"))).toBe("Composing 40 %");
    expect(jobLabel(job("failed", [], "emotion_regenerate"))).toBe("Retouching · failed");
    expect(jobLabel(job("succeeded", [], "song"))).toBe("Composing · ready");
  });
});
