// Step rail (UXA §2.2: 64 px, 8 skewed chips, progress pips for background jobs). Owner: Builder B.
import { useJob } from "@/client/hooks";
import type { CreationStep, GenerationJob } from "@/contract/types";
import { CREATION_STEPS } from "@/contract/types";
import { cx } from "@/ui/cx";
import { useWizard } from "./context";
import { isRunning } from "./generate";
import { gateFrom, reachable, STEP_LABEL, stepIndex } from "./gates";
import s from "./wizard.module.css";

export function StepRail() {
  const { step, character, facts, goStep, edit, world, jobs, exit } = useWizard();
  const draft = useJob(jobs.profile_draft).data;
  const portrait = useJob(jobs.portrait_candidates ?? jobs.portrait_tweak).data;
  const emotions = useJob(jobs.emotion_set).data;
  const song = useJob(jobs.song).data;
  const pip: Partial<Record<CreationStep, GenerationJob | undefined>> = {
    profile: draft, portrait, emotions, theme: song,
  };
  const furthest = character ? stepIndex(character.creationStep ?? "profile") : 0;
  const cur = stepIndex(step);
  return (
    <header className={s.rail}>
      <button type="button" className={s.railExit} onClick={exit} aria-label={edit ? "Back to the profile" : "Back to the hub"}>
        <span aria-hidden="true">◂</span>
      </button>
      <div className={s.railTitle}>
        <span className={s.railKicker}>{edit ? "Editing" : "Summoning"} · {world?.name ?? "…"}</span>
        <span className={s.railName}>{character?.profile.name || (edit ? "Character" : "New character")}</span>
      </div>
      <nav aria-label="Wizard steps">
        <ol className={s.steps}>
          {CREATION_STEPS.map((st, i) => {
            const open = edit ? !!character && (st !== "seed") : st === "seed" ? !character : reachable(st, facts) && !!character;
            const done = !edit && (i < cur || i <= furthest) && st !== step && open;
            const job = pip[st];
            const busy = isRunning(job);
            const blocked = !open && i > 0 && character ? gateFrom(CREATION_STEPS[firstBlocked(facts)], facts).reason : undefined;
            return (
              <li key={st} className={s.stepItem}>
                <button
                  type="button"
                  className={cx(s.stepChip, st === step && s.stepCur, done && s.stepDone, !open && st !== step && s.stepLocked)}
                  aria-current={st === step ? "step" : undefined}
                  disabled={!open || st === step}
                  title={blocked}
                  onClick={() => void goStep(st)}
                >
                  <span className={s.stepNum}>{String(i + 1).padStart(2, "0")}</span>
                  <span className={s.stepLabel}>{STEP_LABEL[st]}</span>
                  {busy && job && (
                    <span className={s.stepPip} role="status" aria-label={`${STEP_LABEL[st]} running, ${Math.round(job.progress * 100)} %`}>
                      <span style={{ transform: `scaleX(${Math.max(0.06, job.progress)})` }} />
                    </span>
                  )}
                  {!busy && job && (job.status === "partial" || job.status === "failed") && <span className={s.stepWarn} aria-label="needs attention">!</span>}
                </button>
              </li>
            );
          })}
        </ol>
      </nav>
    </header>
  );
}

function firstBlocked(f: Parameters<typeof gateFrom>[1]): number {
  for (let i = 0; i < CREATION_STEPS.length - 1; i++) if (!gateFrom(CREATION_STEPS[i], f).ok) return i;
  return 0;
}
