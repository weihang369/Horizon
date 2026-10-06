// Generation jobs (doc 05 GenerationJob, CHR-03..10, APP-07 timings). Owner: EE.
// Tasks run N-in-parallel on the virtual clock with a progress tick, a preview at 50 %, per-task cost and ledger
// rows, and scenario faults (all / partial / song). Jobs live in the client, so they survive navigation.
import type {
  Character, Emotion, EmotionAsset, GenerationJob, GenerationTask, ThemeSong, UsageRecord,
} from "../../contract/types";
import { HorizonError } from "../../contract/errors";
import type { JobEvent, StartJobInput } from "../../client/HorizonClient";
import type { PricingTable } from "../../domain/cost";
import { round6 } from "../../domain/cost";
import { themeSpecFromBrief } from "../../audio/synth/spec";
import { shadowDataUrl, specFromAppearance } from "../../vfx/shadow";
import { draftFromSeed, regenerateField } from "../banks/drafts";
import type { Dataset } from "../db/dataset";
import type { Faults } from "../scenarios";
import type { Scheduler } from "../time/Scheduler";
import type { TimingConfig } from "../timing.config";

export interface JobHost {
  db: Dataset;
  timing: TimingConfig;
  pricing: PricingTable;
  sched: Scheduler;
  newId(prefix: string): string;
  iso(): string;
  jobFault(): Faults["job"];
  emitJob(e: JobEvent, characterName?: string): void;
  ledger(row: Omit<UsageRecord, "id" | "at">): void;
  changed(kind: "character" | "job", id: string): void;
}

const LEAN_EMOTIONS: Emotion[] = ["happy", "sad", "angry"];
const ALL_EMOTIONS: Emotion[] = ["happy", "sad", "angry", "surprised", "thinking", "embarrassed"];
const VFX: Record<Emotion, EmotionAsset["vfxPreset"]> = {
  neutral: "none", happy: "sparkle", sad: "rain", angry: "anger", surprised: "shock", thinking: "ponder", embarrassed: "blush",
};

export interface Plan { task: GenerationTask; ms: number; cost: number; category: UsageRecord["category"]; model: string }

/** Exported for the shared backend fixtures (`npm run fixtures:build`); the MockClient's own use is unchanged. */
export function planTasks(h: JobHost, input: StartJobInput, newTaskId: () => string): { plans: Plan[]; parallel: number } {
  const g = h.pricing.generation;
  const t = h.timing;
  const img = h.db.settings.models.image;
  const music = h.db.settings.models.music;
  const chat = h.db.settings.models.chat;
  const lean = h.db.settings.generationMode === "lean";
  const mk = (type: GenerationTask["type"], ms: number, cost: number, category: UsageRecord["category"], model: string, emotion?: Emotion): Plan => ({
    task: { id: newTaskId(), type, ...(emotion ? { emotion } : {}), status: "queued", attempt: 0, maxAttempts: 3 },
    ms, cost, category, model,
  });
  switch (input.kind) {
    case "profile_draft":
      return {
        parallel: 1,
        plans: (["profile", "appearance_summary", "palette_pick", "song_brief"] as const).map((type) => mk(type, t.profileDraftMs / 4, g.profileDraft / 4, "profile", chat)),
      };
    case "profile_regenerate":
      return { parallel: 1, plans: [mk("profile", t.fieldRegenerateMs, g.profileDraft / 4, "profile", chat)] };
    case "portrait_candidates": {
      const n = lean ? 1 : 2;
      return { parallel: t.portraitParallel, plans: Array.from({ length: n }, () => mk("portrait_candidate", t.portraitMs, g.portrait, "image", img)) };
    }
    case "portrait_tweak":
      return { parallel: 1, plans: [mk("portrait_candidate", t.portraitMs, g.tweak, "image", img)] };
    case "emotion_set": {
      const emotions = input.emotions ?? (lean ? LEAN_EMOTIONS : ALL_EMOTIONS);
      if (input.technique === "expression_sheet") {
        const sheet = mk("expression_sheet", t.sheetMs, g.expressionSheet, "image", img);
        return { parallel: 1, plans: [sheet, ...emotions.map((e) => mk("emotion_image", 0, 0, "image", img, e))] };
      }
      const plans = emotions.map((e) => mk("emotion_image", t.emotionMs, g.emotionEdit, "image", img, e));
      if (!lean) plans.push(mk("blink_frame", t.emotionMs, g.blinkFrame, "image", img));
      return { parallel: t.emotionParallel, plans };
    }
    case "emotion_regenerate":
      return { parallel: 1, plans: (input.emotions ?? ["happy"]).map((e) => mk("emotion_image", t.emotionMs, g.emotionEdit, "image", img, e)) };
    case "song":
      return { parallel: 1, plans: [mk("theme_song", t.songMs, g.song, "music", music)] };
  }
}

export function estimateJob(h: JobHost, input: StartJobInput): number {
  let n = 0;
  const { plans } = planTasks(h, input, () => `task_${n++}`);
  return round6(plans.reduce((a, p) => a + p.cost, 0));
}

/** Budget gates (CHR-13 AC3, STATE-06). */
export function checkJobBudget(h: JobHost, c: Character, estimate: number): void {
  const s = h.db.settings;
  if (s.spentTodayUsd + estimate > s.budget.dailyCapUsd + 1e-9) throw new HorizonError("daily_budget_exceeded");
  if (c.status === "draft" || c.status === "review") {
    const spent = h.db.ledger.filter((r) => r.characterId === c.id && (r.category === "image" || r.category === "music" || r.category === "profile")).reduce((a, r) => a + r.costUsd, 0);
    if (spent + estimate > s.budget.perCharacterCreationCapUsd + 1e-9) throw new HorizonError("creation_budget_exceeded");
  }
}

interface Running { job: GenerationJob; plans: Map<string, Plan>; progress: Map<string, number>; parallel: number; input: StartJobInput; failPlan: Set<string>; stop?: () => void }

export class JobRunner {
  private running = new Map<string, Running>();
  private h: JobHost;
  constructor(h: JobHost) { this.h = h; }

  start(input: StartJobInput): GenerationJob {
    const h = this.h;
    const c = h.db.characters[input.characterId];
    if (!c) throw new HorizonError("not_found", "Character not found.", { retryable: false });
    const { plans, parallel } = planTasks(h, input, () => h.newId("task"));
    const estimatedCostUsd = round6(plans.reduce((a, p) => a + p.cost, 0));
    checkJobBudget(h, c, estimatedCostUsd);
    const job: GenerationJob = {
      id: h.newId("job"), characterId: c.id, kind: input.kind, ...(input.targetField ? { targetField: input.targetField } : {}),
      status: "queued", progress: 0, estimatedCostUsd, actualCostUsd: 0, tasks: plans.map((p) => p.task), createdAt: h.iso(),
    };
    h.db.jobs[job.id] = job;
    c.activeJobId = job.id;
    if (input.kind === "portrait_candidates" || input.kind === "portrait_tweak") {
      c.appearance.candidates = [
        ...(input.kind === "portrait_tweak" ? c.appearance.candidates : c.appearance.candidates.filter((x) => x.selected)),
        ...plans.map((p) => ({ id: p.task.id.replace(/^task_/, "cand_"), url: "", selected: false, status: "generating" as const })),
      ];
    }
    this.run(job, new Map(plans.map((p) => [p.task.id, p])), parallel, input);
    return structuredClone(job);
  }

  /** Re-attach jobs that were running when the DB was loaded (the seed's in-progress emotion set). */
  resume(job: GenerationJob): void {
    const h = this.h;
    const c = h.db.characters[job.characterId];
    if (!c) return;
    const g = h.pricing.generation;
    const plans = new Map<string, Plan>();
    for (const task of job.tasks) {
      const ms = task.type === "emotion_image" ? h.timing.emotionMs : task.type === "theme_song" ? h.timing.songMs : h.timing.portraitMs;
      const cost = task.type === "emotion_image" ? g.emotionEdit : task.type === "theme_song" ? g.song : g.portrait;
      plans.set(task.id, { task, ms, cost, category: task.type === "theme_song" ? "music" : "image", model: h.db.settings.models.image });
    }
    this.run(job, plans, h.timing.emotionParallel, { characterId: job.characterId, kind: job.kind }, 0.35);
  }

  cancel(jobId: string): void {
    const r = this.running.get(jobId);
    const job = r?.job ?? this.h.db.jobs[jobId];
    if (!job) return;
    r?.stop?.();
    this.running.delete(jobId);
    for (const t of job.tasks) {
      if (t.status === "running" && r) {
        const p = r.plans.get(t.id)!;
        if (p.category === "image") this.charge(job, p); // "Images already in progress may still be charged."
      }
      if (t.status === "queued" || t.status === "running") t.status = "skipped";
    }
    job.status = "cancelled";
    job.finishedAt = this.h.iso();
    this.finishCommon(job);
  }

  retryTask(jobId: string, taskId: string): void {
    const job = this.h.db.jobs[jobId];
    const task = job?.tasks.find((t) => t.id === taskId);
    if (!job || !task || task.status !== "failed") return;
    if (task.attempt >= task.maxAttempts) throw new HorizonError("conflict", "This task has used all its retries.", { retryable: false });
    task.status = "queued";
    task.error = undefined;
    const r = this.running.get(jobId);
    if (r) return; // the runner picks it up
    const c = this.h.db.characters[job.characterId];
    const plans = new Map<string, Plan>();
    const g = this.h.pricing.generation;
    for (const t of job.tasks) {
      const ms = t.type === "theme_song" ? this.h.timing.songMs : t.type === "portrait_candidate" ? this.h.timing.portraitMs : this.h.timing.emotionMs;
      const cost = t.type === "theme_song" ? g.song : t.type === "portrait_candidate" ? g.portrait : g.emotionEdit;
      plans.set(t.id, { task: t, ms, cost, category: t.type === "theme_song" ? "music" : "image", model: this.h.db.settings.models.image });
    }
    if (c) c.activeJobId = job.id;
    job.status = "running";
    job.finishedAt = undefined;
    this.run(job, plans, 2, { characterId: job.characterId, kind: job.kind });
  }

  stopAll(): void {
    for (const r of this.running.values()) r.stop?.();
    this.running.clear();
  }

  private run(job: GenerationJob, plans: Map<string, Plan>, parallel: number, input: StartJobInput, startAt = 0): void {
    const h = this.h;
    const fault = h.jobFault();
    const failPlan = new Set<string>();
    const imageTasks = job.tasks.filter((t) => t.type === "portrait_candidate" || t.type === "emotion_image" || t.type === "expression_sheet");
    if (fault === "all") imageTasks.forEach((t) => failPlan.add(t.id));
    if (fault === "partial" && imageTasks.length) failPlan.add((imageTasks[1] ?? imageTasks[0]).id);
    if (fault === "song") job.tasks.filter((t) => t.type === "theme_song").forEach((t) => failPlan.add(t.id));
    const r: Running = { job, plans, progress: new Map(job.tasks.map((t) => [t.id, t.status === "succeeded" || t.status === "failed" ? 1 : t.status === "running" ? startAt : 0])), parallel, input, failPlan };
    this.running.set(job.id, r);
    job.status = "running";
    job.startedAt ??= h.iso();
    r.stop = h.sched.every(h.timing.jobTickMs, () => this.tick(r), `job:${job.id}`);
    this.tick(r);
  }

  private tick(r: Running): boolean {
    const h = this.h;
    const { job } = r;
    const sheet = job.tasks.find((t) => t.type === "expression_sheet");
    let active = job.tasks.filter((t) => t.status === "running").length;
    for (const t of job.tasks) {
      if (active >= r.parallel) break;
      if (t.status !== "queued") continue;
      if (sheet && t !== sheet && t.type === "emotion_image") continue; // sliced from the sheet
      t.status = "running";
      t.attempt += 1;
      active++;
      h.emitJob({ type: "task.update", jobId: job.id, task: structuredClone(t) });
    }
    for (const t of job.tasks) {
      if (t.status !== "running") continue;
      const p = r.plans.get(t.id)!;
      const prev = r.progress.get(t.id) ?? 0;
      const next = p.ms > 0 ? Math.min(1, prev + h.timing.jobTickMs / p.ms) : 1;
      r.progress.set(t.id, next);
      const fails = r.failPlan.has(t.id) && (t.attempt <= 1 || [...r.failPlan].length > 1 && h.jobFault() === "all");
      if (fails && next >= 0.6) {
        t.status = "failed";
        t.error = { code: "provider_error", message: "The image provider returned an error.", retryable: true };
        r.progress.set(t.id, 1);
        if (t.type === "portrait_candidate") this.markCandidate(job, t.id, "failed");
        if (t.type === "expression_sheet") {
          for (const x of job.tasks) if (x.type === "emotion_image" && x.status === "queued") x.status = "skipped";
        }
        h.emitJob({ type: "task.update", jobId: job.id, task: structuredClone(t) });
        continue;
      }
      if (prev < 0.5 && next >= 0.5 && (t.type === "portrait_candidate" || t.type === "emotion_image")) {
        t.previewUrl = this.portraitFor(job, t);
        h.emitJob({ type: "task.update", jobId: job.id, task: structuredClone(t) });
      }
      if (next >= 1) {
        t.status = "succeeded";
        this.charge(job, p);
        this.apply(job, t, r.input);
        if (t.type === "expression_sheet") {
          for (const x of job.tasks) {
            if (x.type !== "emotion_image" || x.status !== "queued") continue;
            x.status = "succeeded";
            x.attempt = 1;
            r.progress.set(x.id, 1);
            this.apply(job, x, r.input);
            h.emitJob({ type: "task.update", jobId: job.id, task: structuredClone(x) });
          }
        }
        h.emitJob({ type: "task.update", jobId: job.id, task: structuredClone(t) });
      }
    }
    const total = job.tasks.length || 1;
    job.progress = Math.round((job.tasks.reduce((a, t) => a + (r.progress.get(t.id) ?? 0), 0) / total) * 1000) / 1000;
    const pending = job.tasks.some((t) => t.status === "queued" || t.status === "running");
    if (!pending) {
      const ok = job.tasks.filter((t) => t.status === "succeeded").length;
      const failed = job.tasks.filter((t) => t.status === "failed").length;
      job.status = failed === 0 ? "succeeded" : ok === 0 ? "failed" : "partial";
      if (job.status === "failed") job.error = { code: "provider_error", message: "Generation failed." };
      job.progress = 1;
      job.finishedAt = h.iso();
      r.stop?.();
      this.running.delete(job.id);
      this.finishCommon(job);
      return false;
    }
    h.emitJob({ type: "job.progress", job: structuredClone(job) });
    h.changed("job", job.id);
    return true;
  }

  private finishCommon(job: GenerationJob): void {
    const c = this.h.db.characters[job.characterId];
    if (c?.activeJobId === job.id) c.activeJobId = undefined;
    if (c) {
      c.updatedAt = this.h.iso();
      this.h.changed("character", c.id);
    }
    this.h.changed("job", job.id);
    this.h.emitJob({ type: "job.done", job: structuredClone(job) }, c?.profile.name);
  }

  private charge(job: GenerationJob, p: Plan): void {
    job.actualCostUsd = round6(job.actualCostUsd + p.cost);
    if (p.cost > 0) this.h.ledger({ category: p.category, model: p.model, characterId: job.characterId, jobId: job.id, costUsd: p.cost, estimatedCostUsd: p.cost });
  }

  private portraitFor(job: GenerationJob, t: GenerationTask): string {
    const c = this.h.db.characters[job.characterId]!;
    const cand = t.type === "portrait_candidate" ? (job.tasks.filter((x) => x.type === "portrait_candidate").indexOf(t) % 2 === 1 ? 2 : 1) : 1;
    return shadowDataUrl(specFromAppearance(c.appearance, c.paletteId, t.emotion ?? "neutral", t.type === "blink_frame" ? "blink" : "default", { candidate: cand as 1 | 2 }));
  }

  private markCandidate(job: GenerationJob, taskId: string, status: "ready" | "failed", url = ""): void {
    const c = this.h.db.characters[job.characterId];
    const cand = c?.appearance.candidates.find((x) => x.id === taskId.replace(/^task_/, "cand_"));
    if (cand) {
      cand.status = status;
      cand.url = url;
    }
  }

  private apply(job: GenerationJob, t: GenerationTask, input: StartJobInput): void {
    const h = this.h;
    const c = h.db.characters[job.characterId];
    if (!c) return;
    const now = h.iso();
    switch (t.type) {
      case "profile": {
        if (job.kind === "profile_regenerate" && input.targetField) {
          Object.assign(c.profile, regenerateField(c.profile, input.targetField, t.attempt + c.version));
        } else {
          const d = draftFromSeed(c.seedPrompt, c.intent);
          c.profile = d.profile;
          c.advisory = d.advisory;
          c.creationStep = "profile";
        }
        break;
      }
      case "appearance_summary": {
        const d = draftFromSeed(c.seedPrompt, c.intent);
        c.appearance = { ...c.appearance, attributes: d.attributes, appearanceSummary: d.appearanceSummary };
        break;
      }
      case "palette_pick":
        c.paletteId = draftFromSeed(c.seedPrompt, c.intent).paletteId;
        break;
      case "song_brief": {
        const d = draftFromSeed(c.seedPrompt, c.intent);
        const id = c.themeSongId ?? h.newId("song");
        h.db.songs[id] = {
          id, characterId: c.id, status: "pending", brief: d.brief, instrumental: true,
          licenseNote: "Placeholder: procedural WebAudio sketch (D-52).",
        };
        c.themeSongId = id;
        break;
      }
      case "portrait_candidate": {
        const url = this.portraitFor(job, t);
        t.resultRef = t.id.replace(/^task_/, "cand_");
        this.markCandidate(job, t.id, "ready", url);
        break;
      }
      case "emotion_image":
      case "blink_frame": {
        const emotion = t.emotion ?? "neutral";
        const prior = Object.values(h.db.assets).filter((a) => a.characterId === c.id && a.emotion === emotion && a.variant === (t.type === "blink_frame" ? "blink" : "default"));
        const replaceLater = c.status === "approved" && prior.some((a) => a.isActive);
        const asset: EmotionAsset = {
          id: h.newId("emo"), characterId: c.id, emotion, variant: t.type === "blink_frame" ? "blink" : "default",
          status: "ready", url: this.portraitFor(job, t), vfxPreset: VFX[emotion],
          generation: { model: h.db.settings.models.image, technique: input.technique === "expression_sheet" ? "expression_sheet" : "reference_edit", prompt: input.prompt ?? "", referenceUrls: c.appearance.basePortraitUrl ? [c.appearance.basePortraitUrl] : [], costUsd: r6(this.costOf(t)), jobId: job.id },
          version: prior.length + 1, isActive: !replaceLater,
        };
        h.db.assets[asset.id] = asset;
        t.resultRef = asset.id;
        if (!replaceLater) {
          for (const a of prior) a.isActive = false;
          const ref = { assetId: asset.id, url: asset.url!, vfxPreset: asset.vfxPreset };
          if (t.type === "blink_frame") c.blink = ref;
          else c.emotions[emotion] = ref;
        }
        break;
      }
      case "expression_sheet":
        break;
      case "theme_song": {
        const id = c.themeSongId ?? h.newId("song");
        const prev = h.db.songs[id];
        const brief = input.brief ?? prev?.brief ?? draftFromSeed(c.seedPrompt, c.intent).brief;
        const spec = themeSpecFromBrief(c.id, brief, `${c.profile.name.split(" ")[0]}'s Theme`);
        const song: ThemeSong = {
          id, characterId: c.id, status: "ready",
          // `#….proc.json` lets resolveAudio route it to renderTheme (fetch ignores the fragment).
          url: `data:application/json;base64,${toBase64(JSON.stringify(spec))}#${c.id}.proc.json`,
          durationSec: Math.round(((8 * 4 * 60) / brief.bpm) * 10) / 10, brief, instrumental: true,
          generation: { model: h.db.settings.models.music, prompt: `Instrumental theme: ${brief.vibe}`, costUsd: h.pricing.generation.song, jobId: job.id },
          licenseNote: "Placeholder: procedural WebAudio sketch (D-52). The real theme comes from Google Lyria 3 Clip via OpenRouter.",
        };
        h.db.songs[id] = song;
        c.themeSongId = id;
        break;
      }
    }
    c.updatedAt = now;
    h.changed("character", c.id);
  }

  private costOf(t: GenerationTask): number {
    const g = this.h.pricing.generation;
    return t.type === "blink_frame" ? g.blinkFrame : g.emotionEdit;
  }
}

const r6 = round6;

function toBase64(s: string): string {
  const bytes = new TextEncoder().encode(s);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}
