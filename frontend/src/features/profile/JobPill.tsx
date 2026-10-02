// Background job pill (STATE-02 "Background/job: toast + rail/status pill"). Owner: Builder B.
//
// Prop API (final; Builder A imports it into the hub roster):
//   <JobPill />                          global floating pill (App chrome): every running job, click → its wizard/profile
//   <JobPill characterId="chr_x" />      inline: that character's running job(s); renders nothing when idle
//   <JobPill job={job} />                inline: one job (object or id), shown until it finishes
//   size?: "sm" | "md"   className?: string
import { useEffect, useState } from "react";
import type { CSSProperties, MouseEvent } from "react";
import { useActiveJobs, useCharacter, useCharacters, useJob } from "@/client/hooks";
import type { GenerationJob, GenerationJobKind } from "@/contract/types";
import { navigate, useRoute } from "@/router";
import { PaletteScope } from "@/theme";
import { cx } from "@/ui/cx";
import s from "./JobPill.module.css";

export interface JobPillProps {
  /** Inline pill for this character's running job(s). */
  characterId?: string;
  /** Inline pill for one job (object or id). */
  job?: GenerationJob | string;
  size?: "sm" | "md";
  className?: string;
}

const VERB: Record<GenerationJobKind, string> = {
  profile_draft: "Drafting",
  profile_regenerate: "Rewriting",
  portrait_candidates: "Painting",
  portrait_tweak: "Tweaking",
  emotion_set: "Emotions",
  emotion_regenerate: "Retouching",
  song: "Composing",
};

const running = (j: GenerationJob) => j.status === "queued" || j.status === "running";

type PillState = "run" | "done" | "warn" | "fail";
/** Visual state: running (a task failed mid-run → warn), or the finished outcome. */
export function pillState(j: GenerationJob): PillState {
  if (running(j)) return j.tasks.some((t) => t.status === "failed") ? "warn" : "run";
  if (j.status === "succeeded") return "done";
  if (j.status === "partial") return "warn";
  return "fail";
}
const END_LABEL: Record<GenerationJob["status"], string> = {
  queued: "", running: "", succeeded: "ready", partial: "partly done", failed: "failed", cancelled: "cancelled",
};

/** "Emotions 2/3", "Composing 40 %". */
export function jobLabel(j: GenerationJob): string {
  const verb = VERB[j.kind];
  if (j.kind === "emotion_set" || j.kind === "portrait_candidates") {
    const counted = j.tasks.filter((t) => t.type === "emotion_image" || t.type === "portrait_candidate" || t.type === "blink_frame");
    if (counted.length > 1) return `${verb} ${counted.filter((t) => t.status === "succeeded").length}/${counted.length}`;
  }
  if (!running(j)) return `${verb} · ${END_LABEL[j.status]}`;
  return `${verb} ${Math.round(j.progress * 100)} %`;
}

export function JobPill({ characterId, job, size = "sm", className }: JobPillProps) {
  if (job !== undefined) return <SingleJob job={job} size={size} className={className} />;
  if (characterId) return <CharacterJobs characterId={characterId} size={size} className={className} />;
  return <GlobalJobs className={className} />;
}

function Pill({ job, more = 0, size, className, onClick, style }: { job: GenerationJob; more?: number; size: "sm" | "md"; className?: string; onClick?: (e: MouseEvent) => void; style?: CSSProperties }) {
  const st = pillState(job);
  const body = (
    <>
      {running(job) ? <span className={s.dot} aria-hidden="true" /> : <span className={s.glyph} aria-hidden="true">{st === "done" ? "✓" : "!"}</span>}
      <span className={s.text}>{jobLabel(job)}</span>
      {more > 0 && <span className={s.more}>+{more}</span>}
      <span className={s.track} aria-hidden="true"><span className={s.fill} style={{ transform: `scaleX(${running(job) ? Math.max(0.04, job.progress) : 1})` }} /></span>
    </>
  );
  const cls = cx(s.pill, s[size], st !== "run" && s[st], className);
  const label = `${jobLabel(job)}${more ? `, ${more} more running` : ""}`;
  return onClick ? (
    <button type="button" className={cls} style={style} onClick={onClick} aria-label={`${label}. Open`}>{body}</button>
  ) : (
    <span className={cls} style={style} role="status" aria-label={label}>{body}</span>
  );
}

function SingleJob({ job, size, className }: { job: GenerationJob | string; size: "sm" | "md"; className?: string }) {
  const id = typeof job === "string" ? job : job.id;
  const live = useJob(id).data ?? (typeof job === "string" ? undefined : job);
  if (!live || !running(live)) return null;
  return <Pill job={live} size={size} className={className} />;
}

function CharacterJobs({ characterId, size, className }: { characterId: string; size: "sm" | "md"; className?: string }) {
  const jobs = (useActiveJobs().data ?? []).filter((j) => j.characterId === characterId && running(j));
  const live = useJob(jobs[0]?.id).data;
  if (!jobs.length) return null;
  const head = live && running(live) ? live : jobs[0];
  return <Pill job={head} more={jobs.length - 1} size={size} className={className} />;
}

/** How long a finished job's outcome stays on the global pill (then the toast/history carry it). */
const LINGER_MS = 4000;
/** Ceremonial screens and screens that own their own job UI or bottom dock. */
const HIDDEN_ON = new Set(["title", "onboarding", "wizard", "profile", "session", "verdict", "dev"]);

function GlobalJobs({ className }: { className?: string }) {
  const route = useRoute();
  const onHub = route.name === "hub";
  // Hub: the roster cards carry this world's jobs inline (the reserved slot), so only other worlds' jobs remain here.
  const here = useCharacters(onHub ? route.worldId : null).data;
  const jobs = (useActiveJobs().data ?? []).filter((j) => running(j) && !(onHub && (!here || here.some((x) => x.id === j.characterId))));
  const head = jobs[0];
  // The last job we showed, so its outcome (ready / failed) can linger briefly after it leaves the active list.
  const [tail, setTail] = useState<string | null>(null);
  useEffect(() => {
    if (head) setTail(head.id);
  }, [head?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const live = useJob(head?.id ?? tail).data;
  const finished = !head && live && live.id === tail && !running(live) ? live : null;
  useEffect(() => {
    if (!finished) return;
    const t = window.setTimeout(() => setTail(null), LINGER_MS);
    return () => window.clearTimeout(t);
  }, [finished?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const job = head ? (live && live.id === head.id ? live : head) : finished;
  const c = useCharacter(job?.characterId).data;
  if (!job || HIDDEN_ON.has(route.name)) return null;
  // On the hub it tucks under the top-right audio cluster instead of floating over the roster.
  if (onHub && (!c || c.worldId === route.worldId)) return null;
  const open = () => {
    if (!c) return;
    if (c.status === "draft" || c.status === "review") navigate({ name: "wizard", worldId: c.worldId, characterId: c.id, step: c.creationStep ?? "profile" });
    else navigate({ name: "profile", worldId: c.worldId, characterId: c.id, tab: job.kind === "song" ? "theme" : "gallery" });
  };
  return (
    <PaletteScope paletteId={c?.paletteId} className={cx(s.floating, onHub && s.top, finished && s.leaving, className)}>
      {c && <span className={s.who}>{c.profile.name || "New character"}</span>}
      <Pill job={job} more={head ? jobs.length - 1 : 0} size="md" onClick={open} />
    </PaletteScope>
  );
}
