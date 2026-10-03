// Generation plumbing for the wizard and profile (CHR-13): estimates, the once-per-launch cost confirm (O04),
// key gating (O05), and a per-character memory of the latest job per kind (jobs live in the client, so they
// survive navigation; this map only remembers which job a step belongs to). Owner: Builder B.
import { useEffect, useMemo, useState } from "react";
import { openOverlay } from "@/app/layers";
import { ui } from "@/stores/ui";
import { reportError } from "@/app/errors";
import { client } from "@/client";
import type { StartJobInput } from "@/client/HorizonClient";
import { useActiveJobs } from "@/client/hooks";
import type { GenerationJob, GenerationJobKind } from "@/contract/types";

/** Drafts created during this app session: "Discard" deletes them (resumed drafts only drop unsaved edits). */
export const createdThisSession = new Set<string>();

// ── Job memory ───────────────────────────────────────────────────────────────
type JobMap = Partial<Record<GenerationJobKind, string>>;
const memory = new Map<string, JobMap>();
const listeners = new Set<() => void>();

export function rememberJob(job: Pick<GenerationJob, "id" | "characterId" | "kind">): void {
  memory.set(job.characterId, { ...memory.get(job.characterId), [job.kind]: job.id });
  listeners.forEach((l) => l());
}

export function forgetJob(characterId: string, kind: GenerationJobKind): void {
  const m = { ...memory.get(characterId) };
  delete m[kind];
  memory.set(characterId, m);
  listeners.forEach((l) => l());
}

/** Latest job id per kind for a character: remembered ids, overridden by any job still running. */
export function useCharacterJobs(characterId: string | null | undefined): JobMap {
  const [, bump] = useState(0);
  useEffect(() => {
    const l = () => bump((x) => x + 1);
    listeners.add(l);
    return () => void listeners.delete(l);
  }, []);
  const active = useActiveJobs().data;
  const remembered = characterId ? memory.get(characterId) : undefined;
  return useMemo(() => {
    const out: JobMap = { ...remembered };
    for (const j of active ?? []) if (j.characterId === characterId) out[j.kind] = j.id;
    return out;
  }, [active, characterId, remembered]);
}

// ── Estimates ────────────────────────────────────────────────────────────────
const estCache = new Map<string, number>();

/** "≈ $X.XX" for a Generate button (CHR-13 AC1). null until known. */
export function useEstimate(input: StartJobInput | null): number | null {
  const key = input ? JSON.stringify(input) : "";
  const [v, setV] = useState<number | null>(() => (key ? estCache.get(key) ?? null : null));
  useEffect(() => {
    if (!input) return setV(null);
    const hit = estCache.get(key);
    if (hit !== undefined) return setV(hit);
    let live = true;
    client.jobs.estimate(input).then((r) => {
      estCache.set(key, r.estimatedCostUsd);
      if (live) setV(r.estimatedCostUsd);
    }).catch(() => {});
    return () => void (live = false);
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return v;
}

// ── Start with confirm ───────────────────────────────────────────────────────
let confirmedThisLaunch = false;
/** Test hook. */
export const resetLaunchConfirm = () => void (confirmedThisLaunch = false);

/**
 * Start a generation job the CHR-13 way: no key → O05; first generation this launch (and the setting is on) →
 * O04 with the estimate; budget and other failures route through reportError. Resolves to the job, or null when
 * cancelled/blocked (the caller keeps every input).
 */
export async function startGeneration(input: StartJobInput, label: string, opts: { confirm?: boolean } = {}): Promise<GenerationJob | null> {
  try {
    const settings = await client.settings.get();
    if (settings.openRouterKeyStatus !== "set") {
      openOverlay("O05", { reason: settings.openRouterKeyStatus === "invalid" ? undefined : `${label} needs your OpenRouter key.` });
      return null;
    }
    if (opts.confirm !== false && settings.cost.confirmBeforeGenerate && !confirmedThisLaunch) {
      const { estimatedCostUsd } = await client.jobs.estimate(input);
      const ok = await new Promise<boolean>((resolve) => {
        let settled = false;
        const settle = (v: boolean) => {
          if (settled) return;
          settled = true;
          off();
          resolve(v);
        };
        const key = openOverlay("O04", { label, estimateUsd: estimatedCostUsd, onConfirm: () => settle(true) });
        // Closing the layer without confirming (Not now, ×, Esc, backdrop) = cancel.
        const off = ui.subscribe((st) => {
          if (!st.layers.some((l) => l.key === key)) queueMicrotask(() => settle(false));
        });
      });
      if (!ok) return null;
      confirmedThisLaunch = true;
    }
    const job = await client.jobs.start(input);
    rememberJob(job);
    return job;
  } catch (err) {
    reportError(err, { context: `${label} needs your OpenRouter key.` });
    return null;
  }
}


export async function retryJobTask(jobId: string, taskId: string): Promise<void> {
  try {
    await client.jobs.retryTask(jobId, taskId);
  } catch (err) {
    reportError(err);
  }
}

export async function cancelJob(jobId: string): Promise<void> {
  try {
    await client.jobs.cancel(jobId);
  } catch (err) {
    reportError(err);
  }
}

export const JOB_VERB: Record<GenerationJobKind, string> = {
  profile_draft: "Drafting",
  profile_regenerate: "Rewriting",
  portrait_candidates: "Painting",
  portrait_tweak: "Tweaking",
  emotion_set: "Emotions",
  emotion_regenerate: "Retouching",
  song: "Composing",
};

export const isRunning = (j: GenerationJob | null | undefined): boolean => !!j && (j.status === "queued" || j.status === "running");
