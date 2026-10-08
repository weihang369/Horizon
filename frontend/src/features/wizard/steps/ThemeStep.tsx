// S05g THEME (CHR-10, D-44): one theme song per character. The AI drafts an editable brief; Compose runs in the
// background; Regenerate replaces; failures offer Retry or "Approve without song". Owner: Builder B.
import { useEffect } from "react";
import { useJob, useSong } from "@/client/hooks";
import type { SongBrief } from "@/contract/types";
import { Button, ChipGroup, ErrorTape, Slider, Tape, TextField } from "@/ui";
import { cx } from "@/ui/cx";
import { Composing, ThemePlayer } from "@/features/profile/ThemePlayer";
import { ActionBar } from "../ActionBar";
import { useWizard } from "../context";
import { isRunning, startGeneration, useEstimate } from "../generate";
import { DEFAULT_BRIEF, GENRES, INSTRUMENTS, MOODS } from "../options";
import s from "./steps.module.css";

const withExtra = (opts: { value: string; label: string }[], cur: string[]) => [...opts, ...cur.filter((v) => !opts.some((o) => o.value === v)).map((v) => ({ value: v, label: v }))];

export function ThemeStep() {
  const { character: c, jobs, work, goStep } = useWizard();
  const song = useSong(c?.id).data;
  const job = useJob(jobs.song).data;
  const brief: SongBrief = work.w.brief ?? song?.brief ?? DEFAULT_BRIEF;
  const est = useEstimate(c ? { characterId: c.id, kind: "song" } : null);
  useEffect(() => {
    if (!work.w.brief && song?.brief) work.setBrief(song.brief);
  }, [song?.brief]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!c) return null;

  const set = (patch: Partial<SongBrief>) => work.setBrief({ ...brief, ...patch });
  const composing = isRunning(job);
  const failed = !composing && (job?.status === "failed" || song?.status === "failed");
  const ready = song?.status === "ready" && !!song.url;
  const compose = () => void startGeneration({ characterId: c.id, kind: "song", brief }, ready ? "Regenerate theme" : "Compose theme");

  return (
    <>
      <section className={cx(s.work, s.workScroll)} aria-labelledby="theme-h">
        <div className={s.stepHead}>
          <div>
            <Tape tone="ink" size="sm">Step 07 · Theme</Tape>
            <h1 id="theme-h" className={s.stepTitle}>{composing ? "Composing…" : ready ? "Their theme" : "Write the brief"}</h1>
          </div>
          <div className={s.stepHeadRight}>
            <span className={s.microNote}>Exactly one theme per character. Regenerating replaces it.</span>
          </div>
        </div>
        <div className={s.themeLayout}>
          <div className={s.brief}>
            <ChipGroup label="Genre · up to 2" multiple max={2} value={brief.genres} options={withExtra(GENRES, brief.genres)} onChange={(v) => set({ genres: v })} />
            <ChipGroup label="Mood · up to 3" multiple max={3} value={brief.moods} options={withExtra(MOODS, brief.moods)} onChange={(v) => set({ moods: v })} />
            <Slider label="Tempo" min={60} max={160} step={2} value={brief.bpm} format={(v) => `${v} BPM`} onChange={(v) => set({ bpm: v })} />
            <ChipGroup label="Instruments · up to 4" multiple max={4} value={brief.instruments} options={withExtra(INSTRUMENTS, brief.instruments)} onChange={(v) => set({ instruments: v })} />
            <TextField label="Vibe" maxLength={120} counter value={brief.vibe} placeholder="Bright city-pop, synth bells, slap bass" onChange={(e) => set({ vibe: e.target.value })} />
          </div>
          <div className={s.themeSide}>
            {composing && job && <Composing progress={job.progress} />}
            {!composing && ready && song && <ThemePlayer song={song} characterName={work.w.profile.name || c.profile.name || "Their"} />}
            {failed && (
              <ErrorTape message="The composer stalled." code={job?.error?.code} action={{ label: "Retry", run: compose, cost: est ?? undefined }} />
            )}
            {!composing && !ready && !failed && (
              <div className={s.themeEmpty}>
                <span className={s.themeEmptyGlyph} aria-hidden="true">♪</span>
                <p>No theme yet. Compose one from the brief: it plays on their profile, in 1:1 chat, and when they're summoned.</p>
              </div>
            )}
            <div className={s.themeActions}>
              <Button variant={ready ? "secondary" : "primary"} cost={est ?? undefined} disabled={composing} onClick={compose}>
                {ready ? "↻ Regenerate (replaces)" : failed ? "Retry compose" : "Compose ▸"}
              </Button>
              {failed && <Button variant="ghost" onClick={() => void goStep("approve")}>Approve without song</Button>}
            </div>
            <p className={s.fine}>Music: {song?.generation?.model ?? "google/lyria-3-clip-preview"} · instrumental · {song?.licenseNote ?? "Placeholder: procedural WebAudio sketch (D-52)."}</p>
          </div>
        </div>
      </section>
      <ActionBar note={composing ? <span className={s.gateNote}>Composing continues in the background.</span> : undefined}>
        <Button variant="primary" size="lg" onClick={() => void goStep("approve")}>Next: Approve ▸</Button>
      </ActionBar>
    </>
  );
}
