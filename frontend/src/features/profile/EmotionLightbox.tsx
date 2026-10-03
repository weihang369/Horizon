// O06 Emotion lightbox (PRF-02 AC2, CHR-08 AC4): big face with its VFX, ←/→ through the 7 emotions, Regenerate
// (cost), "Doesn't look like them" (consistency hint), Download. Owner: Builder B.
import { useEffect, useState } from "react";
import type { OverlayComponentProps } from "@/app/overlayTypes";
import { useCharacter, useJob } from "@/client/hooks";
import type { Emotion } from "@/contract/types";
import { EMOTIONS } from "@/contract/types";
import { emotionMeta, PortraitCard } from "@/character";
import { paletteClass } from "@/theme";
import { Button, IconButton, CloseIcon, Kbd, Tape } from "@/ui";
import { cx } from "@/ui/cx";
import { isRunning, rememberJob, startGeneration, useCharacterJobs, useEstimate } from "@/features/wizard/generate";
import { useAssetCompareWatcher } from "./compare";
import s from "./profile-overlays.module.css";

export function EmotionLightbox({ close, characterId, emotion: initial }: OverlayComponentProps<"O06">) {
  const c = useCharacter(characterId).data;
  const [emotion, setEmotion] = useState<Emotion>(initial);
  const jobs = useCharacterJobs(characterId);
  const regenJob = useJob(jobs.emotion_regenerate).data;
  useAssetCompareWatcher(c, jobs.emotion_regenerate);
  const est = useEstimate({ characterId, kind: "emotion_regenerate", emotions: [emotion] });
  const busyHere = isRunning(regenJob) && regenJob!.tasks.some((t) => t.emotion === emotion);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      setEmotion((cur) => {
        const i = EMOTIONS.indexOf(cur);
        return EMOTIONS[(i + (e.key === "ArrowRight" ? 1 : EMOTIONS.length - 1)) % EMOTIONS.length];
      });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!c) return null;
  const meta = emotionMeta[emotion];
  const ref = c.emotions[emotion];
  const approved = c.status === "approved";
  const regenerate = async (hint?: string) => {
    const job = await startGeneration(
      { characterId, kind: "emotion_regenerate", emotions: [emotion], ...(hint ? { prompt: hint } : {}) },
      hint ? `Redo ${meta.label.toLowerCase()} (consistency)` : `Regenerate ${meta.label.toLowerCase()}`,
    );
    if (job) rememberJob(job);
  };
  const step = (d: number) => setEmotion(EMOTIONS[(EMOTIONS.indexOf(emotion) + d + EMOTIONS.length) % EMOTIONS.length]);

  return (
    <div className={cx(paletteClass(c.paletteId), s.lightbox)} role="dialog" aria-modal="true" aria-label={`${c.profile.name}, ${meta.label}`}>
      <div className={s.lbHead}>
        <Tape tone="primary" size="sm">O06 · Gallery</Tape>
        <h2 className={s.lbTitle}>{c.profile.name.split(" ")[0]} · <span>{meta.label}</span></h2>
        <IconButton label="Close" onClick={close} className={s.lbClose}><CloseIcon width={18} height={18} /></IconButton>
      </div>
      <div className={s.lbBody}>
        <button type="button" className={cx(s.lbArrow, s.lbPrev)} onClick={() => step(-1)} aria-label="Previous emotion">◂</button>
        <div className={s.lbStage}>
          <PortraitCard key={emotion} character={c} emotion={emotion} size="hero" width="var(--lb-w)" />
          {busyHere && <span className={s.lbBusy}><Tape tone="ink">Repainting…</Tape></span>}
          {!ref && !busyHere && <span className={s.lbMissing}><Tape tone="warn" size="sm">No art yet · neutral + VFX fallback</Tape></span>}
        </div>
        <button type="button" className={cx(s.lbArrow, s.lbNext)} onClick={() => step(1)} aria-label="Next emotion">▸</button>
        <aside className={s.lbSide}>
          <div className={s.lbMeta}>
            <span className={s.lbGlyph} aria-hidden="true">{meta.icon}</span>
            <div>
              <p className={s.lbName}>{meta.label}</p>
              <p className={s.lbSub}>VFX · {meta.vfx} · MANUAL key <Kbd>Alt+{meta.hotkey}</Kbd></p>
            </div>
          </div>
          {emotion === "neutral" ? (
            <p className={s.lbNote}>Neutral is the locked base portrait. Change it from Edit → Portrait.</p>
          ) : (
            <div className={s.lbActions}>
              <Button variant="primary" cost={est ?? undefined} disabled={busyHere} onClick={() => void regenerate()}>↻ {ref ? "Regenerate" : "Generate"}</Button>
              {ref && (
                <Button variant="secondary" cost={est ?? undefined} disabled={busyHere} onClick={() => void regenerate("Doesn't look like them: keep identity consistent with the base portrait.")}>
                  Doesn't look like them
                </Button>
              )}
              {approved && ref && <p className={s.lbNote}>The current face stays active until you pick Old or New.</p>}
            </div>
          )}
          {ref && (
            <a className={s.lbDownload} href={ref.url} download={`${c.profile.name.replace(/\s+/g, "_")}_${emotion}.svg`}>⤓ Download</a>
          )}
          <p className={s.lbHint}><Kbd>←</Kbd> <Kbd>→</Kbd> browse · <Kbd>Esc</Kbd> close</p>
        </aside>
      </div>
      <div className={s.lbStrip} role="tablist" aria-label="Emotions">
        {EMOTIONS.map((e) => (
          <button
            key={e}
            type="button"
            role="tab"
            aria-selected={e === emotion}
            className={cx(s.lbThumb, e === emotion && s.lbThumbOn, !c.emotions[e] && s.lbThumbMissing)}
            onClick={() => setEmotion(e)}
          >
            {c.emotions[e] ? <img src={c.emotions[e]!.url} alt="" draggable={false} /> : <span aria-hidden="true">{emotionMeta[e].icon}</span>}
            <span className={s.lbThumbLabel}>{emotionMeta[e].label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
