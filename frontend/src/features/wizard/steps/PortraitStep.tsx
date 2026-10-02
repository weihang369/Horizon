// S05d PORTRAIT (CHR-07): candidates develop (QUEUED → PAINTING → FINISHING + elapsed), pick → Lock as base,
// regenerate or refine by text (Tweak). Failures are per candidate with Retry. Owner: Builder B.
import { useState } from "react";
import type { CSSProperties } from "react";
import { audio } from "@/audio/engine";
import { reportError } from "@/app/errors";
import { toast } from "@/app/layers";
import { client } from "@/client";
import { useJob, useNow, useSettings } from "@/client/hooks";
import type { GenerationJob, GenerationTask } from "@/contract/types";
import { formatDuration } from "@/domain/format";
import { Button, HalftoneDevelop, Tape, TextField } from "@/ui";
import { cx } from "@/ui/cx";
import { ActionBar } from "../ActionBar";
import { useWizard } from "../context";
import { isRunning, retryJobTask, startGeneration, useEstimate } from "../generate";
import { gateFrom } from "../gates";
import s from "./steps.module.css";

const candOf = (t: GenerationTask) => t.id.replace(/^task_/, "cand_");

function phase(t: GenerationTask | undefined): "QUEUED" | "PAINTING" | "FINISHING" {
  if (!t || t.status === "queued") return "QUEUED";
  return t.previewUrl ? "FINISHING" : "PAINTING";
}

export function PortraitStep() {
  const { character: c, jobs, goStep, facts } = useWizard();
  const settings = useSettings().data;
  const candJob = useJob(jobs.portrait_candidates).data;
  const tweakJob = useJob(jobs.portrait_tweak).data;
  const now = useNow(1000);
  const [tweak, setTweak] = useState("");
  const [locking, setLocking] = useState<string | null>(null);
  const estGen = useEstimate(c ? { characterId: c.id, kind: "portrait_candidates" } : null);
  const estTweak = useEstimate(c ? { characterId: c.id, kind: "portrait_tweak", prompt: "tweak" } : null);
  if (!c) return null;

  const jobsList = [candJob, tweakJob].filter((j): j is GenerationJob => !!j);
  const taskFor = (candId: string): { job: GenerationJob; task: GenerationTask } | null => {
    for (const j of jobsList) {
      const t = j.tasks.find((x) => candOf(x) === candId);
      if (t) return { job: j, task: t };
    }
    return null;
  };
  const busy = jobsList.some(isRunning);
  const cands = c.appearance.candidates;
  const lean = settings?.generationMode !== "standard";
  const gate = gateFrom("portrait", facts);

  const lock = async (id: string) => {
    setLocking(id);
    try {
      await client.characters.lockPortrait(c.id, id);
      audio.playSfx("ui_confirm");
      toast({ variant: "success", text: "Base portrait locked. EMOTIONS unlocked." });
    } catch (err) {
      reportError(err);
    } finally {
      setLocking(null);
    }
  };
  const generate = () => void startGeneration({ characterId: c.id, kind: "portrait_candidates" }, "Generate portrait");
  const applyTweak = async () => {
    const text = tweak.trim();
    if (!text) return;
    const job = await startGeneration({ characterId: c.id, kind: "portrait_tweak", prompt: text }, "Tweak portrait");
    if (job) setTweak("");
  };

  return (
    <>
      <section className={s.work} aria-labelledby="portrait-h">
        <div className={s.stepHead}>
          <div>
            <Tape tone="ink" size="sm">Step 04 · Portrait</Tape>
            <h1 id="portrait-h" className={s.stepTitle}>{busy ? "Developing…" : cands.length ? "Pick a face" : "Paint the portrait"}</h1>
          </div>
          <div className={s.stepHeadRight}>
            <span className={s.microNote}>{lean ? "Lean mode: 1 candidate per run." : "Standard mode: 2 candidates per run."}</span>
          </div>
        </div>

        {cands.length === 0 ? (
          <div className={s.portraitEmpty}>
            <div className={s.ghostCard} aria-hidden="true"><span>?</span></div>
            <div>
              <p className={s.lede}>Your look is set. Paint a first portrait from it, then lock the one you like as the base for every emotion.</p>
              <Button variant="primary" size="lg" cost={estGen ?? undefined} onClick={generate}>Generate portrait ▸</Button>
            </div>
          </div>
        ) : (
          <div className={s.cands} role="list" aria-label="Portrait candidates">
            {cands.map((cand, i) => {
              const tj = taskFor(cand.id);
              const generating = cand.status === "generating" || cand.status === "pending";
              const failed = cand.status === "failed" || tj?.task.status === "failed";
              const ph = phase(tj?.task);
              const started = tj?.job.startedAt ? Date.parse(tj.job.startedAt) : now;
              return (
                <article key={cand.id} role="listitem" className={cx(s.cand, cand.selected && s.candLocked)} style={{ "--i": i } as CSSProperties} aria-label={`Candidate ${i + 1}`}>
                  <div className={s.candFrame}>
                    {cand.url && !failed && <img src={cand.url} alt={`Candidate ${i + 1}`} className={s.candImg} draggable={false} />}
                    {generating && !failed && (
                      <>
                        {tj?.task.previewUrl && <img src={tj.task.previewUrl} alt="" className={cx(s.candImg, s.candPreview)} draggable={false} />}
                        <HalftoneDevelop className={s.candDevelop} label={null} />
                        <div className={s.candSteps} role="status" aria-label={`${ph}, ${formatDuration(now - started)}`}>
                          {(["QUEUED", "PAINTING", "FINISHING"] as const).map((p) => (
                            <span key={p} className={cx(s.candStep, p === ph && s.candStepOn, (["QUEUED", "PAINTING", "FINISHING"].indexOf(p) < ["QUEUED", "PAINTING", "FINISHING"].indexOf(ph)) && s.candStepDone)}>{p}</span>
                          ))}
                          <span className={s.candElapsed}>{formatDuration(Math.max(0, now - started))}</span>
                        </div>
                      </>
                    )}
                    {failed && (
                      <div className={s.failed}>
                        <span className={s.failedSlash}>FAILED</span>
                        <p>{tj?.task.error?.message ?? "The image provider returned an error."}</p>
                        {tj && <Button size="sm" variant="secondary" onClick={() => void retryJobTask(tj.job.id, tj.task.id)}>↻ Retry</Button>}
                      </div>
                    )}
                    {cand.selected && <span className={s.lockBadge}>🔒 BASE</span>}
                    {cand.url && !generating && !failed && <span className={s.candPh}>Placeholder · candidate {i + 1}</span>}
                  </div>
                  <div className={s.candActions}>
                    {cand.status === "ready" && !cand.selected && (
                      <Button variant="primary" size="sm" disabled={!!locking} onClick={() => void lock(cand.id)}>
                        {locking === cand.id ? "Locking…" : "Lock as base"}
                      </Button>
                    )}
                    {cand.selected && <span className={s.lockedText}>Locked. Every emotion is edited from this face.</span>}
                  </div>
                </article>
              );
            })}
          </div>
        )}

        {cands.length > 0 && (
          <div className={s.tweakRow}>
            <TextField
              label="Tweak"
              placeholder="shorter hair, warmer smile, add a scarf…"
              value={tweak}
              maxLength={160}
              hint="Refines the base by text (a reference edit)."
              onChange={(e) => setTweak(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void applyTweak()}
            />
            <Button variant="secondary" disabled={!tweak.trim() || !c.appearance.basePortraitUrl && !cands.some((x) => x.status === "ready")} cost={estTweak ?? undefined} onClick={() => void applyTweak()}>Apply tweak</Button>
            <Button variant="ghost" cost={estGen ?? undefined} disabled={busy} onClick={generate}>↻ New candidates</Button>
          </div>
        )}
      </section>
      <ActionBar note={!gate.ok ? <span className={s.gateNote}>{gate.reason}</span> : undefined}>
        <Button variant="primary" size="lg" disabled={!gate.ok} onClick={() => void goStep("emotions")}>Next: Emotions ▸</Button>
      </ActionBar>
    </>
  );
}
