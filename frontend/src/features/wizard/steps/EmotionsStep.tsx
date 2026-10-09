// S05e EMOTIONS (CHR-08): a 7-slot grid (neutral = the locked base) and BOTH reveal variants:
//   B · per-emotion edits: slots develop and fill one by one.
//   C · expression sheet: a contact sheet develops, then a slice cuts it and the tiles fly into their slots (FLIP).
// Lean generates happy/sad/angry now; the rest are "Generate (≈ $0.04)" on demand. Owner: Builder B.
import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { audio } from "@/audio/engine";
import { openOverlay } from "@/app/layers";
import { client } from "@/client";
import { putResource, resKeys } from "@/stores/entities";
import { useJob, useSettings } from "@/client/hooks";
import type { Emotion, GenerationJob, GenerationTask } from "@/contract/types";
import { EMOTIONS } from "@/contract/types";
import { emotionMeta } from "@/character";
import { useMotionPrefs } from "@/motion";
import { Button, HalftoneDevelop, Segmented, Tape } from "@/ui";
import { cx } from "@/ui/cx";
import { shadowDataUrl, specFromAppearance } from "@/vfx";
import { useAssetCompareWatcher } from "@/features/profile/compare";
import { ActionBar } from "../ActionBar";
import { useWizard } from "../context";
import { cancelJob, isRunning, retryJobTask, startGeneration, useEstimate } from "../generate";
import { gateFrom, laterStep } from "../gates";
import s from "./steps.module.css";

export type RevealVariant = "per_emotion" | "expression_sheet";
let variantMemory: RevealVariant = "per_emotion";

const NON_NEUTRAL = EMOTIONS.filter((e) => e !== "neutral");

interface SlotState {
  status: "ready" | "developing" | "queued" | "failed" | "later" | "empty";
  url?: string;
  preview?: string;
  task?: GenerationTask;
  job?: GenerationJob;
}

export function EmotionsStep() {
  const { character: c, jobs, goStep, facts, edit } = useWizard();
  const settings = useSettings().data;
  const prefs = useMotionPrefs();
  const [variant, setVariant] = useState<RevealVariant>(variantMemory);
  const setVar = (v: RevealVariant) => { variantMemory = v; setVariant(v); };
  const setJob = useJob(jobs.emotion_set).data;
  const one = useJob(jobs.emotion_regenerate).data;
  useAssetCompareWatcher(c, jobs.emotion_regenerate);
  const lean = settings?.generationMode !== "standard";
  const est = useEstimate(c ? { characterId: c.id, kind: "emotion_set", technique: variant } : null);
  const estOne = useEstimate(c ? { characterId: c.id, kind: "emotion_regenerate", emotions: ["surprised"] } : null);
  const slotEls = useRef(new Map<Emotion, HTMLElement>());
  const [popped, setPopped] = useState<Set<Emotion>>(new Set());
  const sheetTask = setJob?.tasks.find((t) => t.type === "expression_sheet");
  const isSheet = !!sheetTask;
  const running = isRunning(setJob);

  const slots = useMemo(() => {
    const out = {} as Record<Emotion, SlotState>;
    if (!c) return out;
    for (const e of EMOTIONS) {
      const ref = c.emotions[e];
      const fromSet = setJob?.tasks.find((t) => t.type === "emotion_image" && t.emotion === e);
      const fromOne = one?.tasks.find((t) => t.emotion === e);
      const t = fromOne && (isRunning(one) || fromOne.status === "failed") ? fromOne : fromSet;
      const j = (t === fromOne ? one : setJob) ?? undefined;
      if (t?.status === "running") out[e] = { status: "developing", preview: t.previewUrl, task: t, job: j };
      else if (t?.status === "queued") out[e] = { status: "queued", task: t, job: j };
      else if (t?.status === "failed" && !ref) out[e] = { status: "failed", task: t, job: j };
      else if (ref) out[e] = { status: "ready", url: ref.url };
      else out[e] = { status: e === "neutral" ? "empty" : "later" };
    }
    return out;
  }, [c, setJob, one]);

  // ── Variant C: slice the sheet into the slots when it finishes (FLIP flight) ──
  const sheetRef = useRef<HTMLDivElement>(null);
  const tileEls = useRef(new Map<Emotion, HTMLElement>());
  const [slicing, setSlicing] = useState(false);
  const prevSheet = useRef(sheetTask?.status);
  useEffect(() => {
    const was = prevSheet.current;
    prevSheet.current = sheetTask?.status;
    if (was !== "running" || sheetTask?.status !== "succeeded") return;
    setSlicing(true);
    audio.playSfx("ui_whoosh");
    const targets = (setJob?.tasks ?? []).filter((t) => t.type === "emotion_image" && t.emotion).map((t) => t.emotion!) as Emotion[];
    const timers: number[] = [];
    const flights: Animation[] = [];
    const fly = () => {
      targets.forEach((e, i) => {
        const from = tileEls.current.get(e)?.getBoundingClientRect();
        const to = slotEls.current.get(e)?.getBoundingClientRect();
        const img = tileEls.current.get(e)?.querySelector("img");
        if (!from || !to || !img || prefs.reduced) {
          timers.push(window.setTimeout(() => setPopped((p) => new Set(p).add(e)), prefs.reduced ? 0 : 200 + i * 70));
          return;
        }
        const ghost = img.cloneNode() as HTMLImageElement;
        ghost.className = s.flyer;
        Object.assign(ghost.style, { left: `${from.left}px`, top: `${from.top}px`, width: `${from.width}px`, height: `${from.height}px` });
        document.body.appendChild(ghost);
        const dx = to.left - from.left;
        const dy = to.top - from.top;
        const sx = to.width / from.width;
        const sy = to.height / from.height;
        const a = ghost.animate(
          [
            { transform: "translate(0,0) rotate(0deg) scale(1)", opacity: 1 },
            { transform: `translate(${dx * 0.5}px, ${dy * 0.5 - 40}px) rotate(${i % 2 ? 6 : -6}deg) scale(${(sx + 1) / 2 + 0.08}, ${(sy + 1) / 2 + 0.08})`, opacity: 1, offset: 0.55 },
            { transform: `translate(${dx}px, ${dy}px) rotate(0deg) scale(${sx}, ${sy})`, opacity: 1 },
          ],
          { duration: 560, delay: 260 + i * 80, easing: "cubic-bezier(0.7, 0, 0.2, 1)", fill: "both" },
        );
        flights.push(a);
        a.finished.then(() => {
          setPopped((p) => new Set(p).add(e));
          ghost.remove();
        }).catch(() => ghost.remove());
      });
      timers.push(window.setTimeout(() => setSlicing(false), 260 + targets.length * 80 + 700));
    };
    // Cut lines draw first (260 ms), then the tiles leave.
    requestAnimationFrame(fly);
    return () => {
      timers.forEach(clearTimeout);
      flights.forEach((f) => f.finish());
    };
  }, [sheetTask?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!c) return null;
  const gate = gateFrom("emotions", facts);
  const doneCount = NON_NEUTRAL.filter((e) => slots[e]?.status === "ready").length;
  const blink = setJob?.tasks.find((t) => t.type === "blink_frame");

  const generateSet = () => void startGeneration({ characterId: c.id, kind: "emotion_set", technique: variant }, "Generate emotions").then((j) => {
    if (j && !edit) void client.characters.update(c.id, { creationStep: laterStep(c.creationStep, "emotions") }).catch(() => {});
  });
  const generateOne = (e: Emotion) => void startGeneration({ characterId: c.id, kind: "emotion_regenerate", emotions: [e] }, `Generate ${emotionMeta[e].label.toLowerCase()}`);
  const skip = async () => {
    if (!edit) {
      // The palette gate reads the cached character; prime it with the answer, since over HTTP the refresh only
      // arrives later on the global stream (http-client-parity G11).
      const next = await client.characters.update(c.id, { creationStep: laterStep(c.creationStep, "palette") }).catch(() => null);
      if (next) putResource(resKeys.character(next.id), next);
    }
    void goStep("palette", { skipSave: true });
  };

  const sheetVisible = isSheet && (running || slicing);
  const sheetTargets = (setJob?.tasks ?? []).filter((t) => t.type === "emotion_image" && t.emotion).map((t) => t.emotion!) as Emotion[];

  return (
    <>
      <section className={s.work} aria-labelledby="emo-h">
        <div className={s.stepHead}>
          <div>
            <Tape tone="ink" size="sm">Step 05 · Emotions</Tape>
            <h1 id="emo-h" className={s.stepTitle}>{running ? (isSheet ? "Developing the sheet…" : "Painting faces…") : "Seven faces"}</h1>
          </div>
          <div className={s.stepHeadRight}>
            <Segmented
              label="Reveal variant"
              value={variant}
              onChange={setVar}
              options={[{ value: "per_emotion", label: "B · Per-emotion" }, { value: "expression_sheet", label: "C · Expression sheet" }]}
            />
          </div>
        </div>

        <div className={s.emoStatus} role="status">
          {running && setJob ? (
            <>
              <span className={s.emoBar}><span style={{ transform: `scaleX(${Math.max(0.03, setJob.progress)})` }} /></span>
              <span className={s.emoCount}>{isSheet ? (sheetTask?.status === "running" ? "SHEET DEVELOPING" : "SLICING") : `${setJob.tasks.filter((t) => t.status === "succeeded" && t.type === "emotion_image").length}/${setJob.tasks.filter((t) => t.type === "emotion_image").length} FACES`} · {Math.round(setJob.progress * 100)} %</span>
              <span className={s.microNote}>Runs in the background. You can move on; a pip on the rail tracks it.</span>
              <Button size="sm" variant="ghost" onClick={() => void cancelJob(setJob.id)}>Stop remaining</Button>
            </>
          ) : (
            <>
              <span className={s.emoCount}>{doneCount}/6 FACES READY</span>
              <span className={s.microNote}>
                {lean ? "Lean mode: happy, sad and angry now; the rest on demand." : "Standard mode: all six now, plus a blink frame."}
                {setJob?.status === "partial" ? " Some faces failed: retry them below." : ""}
              </span>
            </>
          )}
          {blink && <Tape tone={blink.status === "succeeded" ? "ok" : blink.status === "failed" ? "error" : "ink"} size="sm">Blink {blink.status === "succeeded" ? "✓" : blink.status === "failed" ? "✕" : "…"}</Tape>}
        </div>

        <div className={s.emoStage}>
          <EmotionSlot e="neutral" st={slots.neutral} base register={(el) => el && slotEls.current.set("neutral", el)} onOpen={() => openOverlay("O06", { characterId: c.id, emotion: "neutral" })} />
          <div className={s.emoGrid}>
            {NON_NEUTRAL.map((e, i) => (
              <EmotionSlot
                key={e}
                e={e}
               
                st={slots[e]}
                index={i}
                hidden={sheetVisible && sheetTargets.includes(e) && !popped.has(e)}
                popped={popped.has(e)}
                register={(el) => el && slotEls.current.set(e, el)}
                onOpen={() => openOverlay("O06", { characterId: c.id, emotion: e })}
                onGenerate={() => generateOne(e)}
                onRetry={(job, task) => void retryJobTask(job.id, task.id)}
                estOne={estOne}
              />
            ))}
            {sheetVisible && (
              <div ref={sheetRef} className={cx(s.sheet, slicing && s.sheetSlicing)} aria-label="Expression sheet developing">
                <div className={s.sheetHead}><span>EXPRESSION SHEET · 4 × 2</span><span>{Math.round((setJob?.progress ?? 0) * 100)} %</span></div>
                <div className={s.sheetGrid}>
                  {(["neutral", ...sheetTargets] as Emotion[]).concat(Array(Math.max(0, 8 - sheetTargets.length - 1)).fill(null)).slice(0, 8).map((e, i) => (
                    <div key={i} className={cx(s.sheetTile, !e && s.sheetTileEmpty, e && popped.has(e) && s.sheetTileGone)} ref={(el) => { if (el && e) tileEls.current.set(e, el); }}>
                      {e && <img src={shadowDataUrl(specFromAppearance(c.appearance, c.paletteId, e, "default"))} alt="" draggable={false} />}
                      {e && <span className={s.sheetLabel}>{emotionMeta[e].label}</span>}
                    </div>
                  ))}
                </div>
                {!slicing && <HalftoneDevelop className={s.sheetDevelop} style={{ "--dev": 1 - (setJob?.progress ?? 0) } as CSSProperties} label={null} />}
                {slicing && <div className={s.cuts} aria-hidden="true"><i /><i /><i /><i /></div>}
              </div>
            )}
          </div>
        </div>
      </section>
      <ActionBar note={!gate.ok ? <span className={s.gateNote}>{gate.reason}</span> : undefined}>
        {!running && doneCount < 6 && (
          <Button variant={gate.ok ? "secondary" : "primary"} size={gate.ok ? "md" : "lg"} cost={est ?? undefined} disabled={!c.appearance.basePortraitUrl} onClick={generateSet}>
            {doneCount ? "Generate set again ▸" : "Generate emotions ▸"}
          </Button>
        )}
        {!gate.ok && <Button variant="ghost" onClick={() => void skip()}>Skip for now</Button>}
        {gate.ok && <Button variant="primary" size="lg" onClick={() => void goStep("palette")}>Next: Palette ▸</Button>}
      </ActionBar>
    </>
  );
}

function EmotionSlot({ e, st, base, index = 0, hidden, popped, register, onOpen, onGenerate, onRetry, estOne }: {
  e: Emotion; st: SlotState | undefined; base?: boolean; index?: number; hidden?: boolean; popped?: boolean;
  register: (el: HTMLElement | null) => void; onOpen: () => void; onGenerate?: () => void;
  onRetry?: (job: GenerationJob, task: GenerationTask) => void; estOne?: number | null;
}) {
  const meta = emotionMeta[e];
  const status = st?.status ?? "later";
  const ready = status === "ready";
  return (
    <div
      ref={register}
      className={cx(s.slot, base && s.slotBase, s[`slot_${status}`], hidden && s.slotHidden, popped && s.slotPop)}
      style={{ "--i": index } as CSSProperties}
    >
      <button type="button" className={s.slotArt} disabled={!ready} onClick={onOpen} aria-label={ready ? `${meta.label}: open lightbox` : `${meta.label}: ${status}`}>
        {ready && st?.url && <img src={st.url} alt="" draggable={false} />}
        {(status === "developing" || status === "queued") && (
          <>
            {st?.preview && <img src={st.preview} alt="" className={s.slotPreview} draggable={false} />}
            <HalftoneDevelop className={s.slotDevelop} label={status === "queued" ? "QUEUED" : "PAINTING"} />
          </>
        )}
        {status === "later" && <span className={s.slotGlyph} aria-hidden="true">{meta.icon}</span>}
        {status === "failed" && <span className={s.failedSlash}>FAILED</span>}
      </button>
      <div className={s.slotFoot}>
        <span className={s.slotKey}>{meta.hotkey}</span>
        <span className={s.slotName}>{meta.label}</span>
        {base && <Tape tone="brand" size="sm">Base</Tape>}
      </div>
      {status === "later" && onGenerate && (
        <button type="button" className={s.slotAction} onClick={onGenerate}>Generate{estOne ? ` (≈ $${estOne.toFixed(2)})` : ""}</button>
      )}
      {status === "failed" && st?.job && st.task && onRetry && (
        <button type="button" className={cx(s.slotAction, s.slotRetry)} onClick={() => onRetry(st.job!, st.task!)}>↻ Retry</button>
      )}
    </div>
  );
}
