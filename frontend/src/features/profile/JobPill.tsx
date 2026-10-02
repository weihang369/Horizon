// Background job pill (STATE-02 "Background/job: toast + rail/status pill"). Owner: Builder B.
//
// Prop API (final; Builder A imports it into the hub roster):
//   <JobPill />                          global floating pill (App chrome): every running job, click → its wizard/profile
//   <JobPill characterId="chr_x" />      inline: that character's running job(s); renders nothing when idle
//   <JobPill job={job} />                inline: one job (object or id), shown until it finishes
//   size?: "sm" | "md"   className?: string
import type { CSSProperties, MouseEvent } from "react";
import { useActiveJobs, useCharacter, useJob } from "@/client/hooks";
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

/** "Emotions 2/3", "Composing 40 %". */
export function jobLabel(j: GenerationJob): string {
  const verb = VERB[j.kind];
  if (j.kind === "emotion_set" || j.kind === "portrait_candidates") {
    const counted = j.tasks.filter((t) => t.type === "emotion_image" || t.type === "portrait_candidate" || t.type === "blink_frame");
    if (counted.length > 1) return `${verb} ${counted.filter((t) => t.status === "succeeded").length}/${counted.length}`;
  }
  return `${verb} ${Math.round(j.progress * 100)} %`;
}

export function JobPill({ characterId, job, size = "sm", className }: JobPillProps) {
  if (job !== undefined) return <SingleJob job={job} size={size} className={className} />;
  if (characterId) return <CharacterJobs characterId={characterId} size={size} className={className} />;
  return <GlobalJobs className={className} />;
}

function Pill({ job, more = 0, size, className, onClick, style }: { job: GenerationJob; more?: number; size: "sm" | "md"; className?: string; onClick?: (e: MouseEvent) => void; style?: CSSProperties }) {
  const failed = job.tasks.some((t) => t.status === "failed");
  const body = (
    <>
      <span className={s.dot} aria-hidden="true" />
      <span className={s.text}>{jobLabel(job)}</span>
      {more > 0 && <span className={s.more}>+{more}</span>}
      <span className={s.track} aria-hidden="true"><span className={s.fill} style={{ transform: `scaleX(${Math.max(0.04, job.progress)})` }} /></span>
    </>
  );
  const cls = cx(s.pill, s[size], failed && s.warn, className);
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

function GlobalJobs({ className }: { className?: string }) {
  const route = useRoute();
  const jobs = (useActiveJobs().data ?? []).filter(running);
  const head = jobs[0];
  const live = useJob(head?.id).data;
  const c = useCharacter(head?.characterId).data;
  // The wizard shows its own rail pips and the profile its own inline pill; both own the bottom-left corner.
  // Session and verdict own the bottom dock (transport, steering, composer), so the pill stays off the stage.
  if (!head || route.name === "wizard" || route.name === "profile" || route.name === "session" || route.name === "verdict") return null;
  const job = live && running(live) ? live : head;
  const open = () => {
    if (!c) return;
    if (c.status === "draft" || c.status === "review") navigate({ name: "wizard", worldId: c.worldId, characterId: c.id, step: c.creationStep ?? "profile" });
    else navigate({ name: "profile", worldId: c.worldId, characterId: c.id, tab: job.kind === "song" ? "theme" : "gallery" });
  };
  return (
    <PaletteScope paletteId={c?.paletteId} className={cx(s.floating, className)}>
      {c && <span className={s.who}>{c.profile.name || "New character"}</span>}
      <Pill job={job} more={jobs.length - 1} size="md" onClick={open} />
    </PaletteScope>
  );
}
