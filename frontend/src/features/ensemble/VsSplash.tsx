// O16 VS splash / Round banner (Builder D). Ceremonies on the conductor (R6, D-55): queued one at a time, any key or
// click skips to the end state in ≤ 120 ms, and input is never blocked (the layer is pointer-events:none).
// VS (1600): 0 split + side stacks fly in · 350 "VS" 2.4→1 + shake + sting · 700 the motion types on an ink tape.
// Banner Slam (1500): 0 ink tape scaleX · 160 gong · ~420 tiles land · 700 in · hold 800 · exit sideways.
import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import type { DebateConfig } from "../../contract/types";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { audio } from "../../audio/engine";
import { PortraitCard } from "../../character";
import { playCeremony, useCeremony, useMotionPrefs } from "../../motion";
import { RansomText, Tape, cx } from "../../ui";
import { debateColumns, useCharMap, useSlot } from "./shared";
import s from "./VsSplash.module.css";

const VS_MS = 1600;
const BANNER_MS = 1500;
let runSeq = 0;

export function VsSplash({ sessionId, kind, label, close }: OverlayComponentProps<"O16">) {
  const [run, setRun] = useState<{ id: string; stage: "vs" | "round" } | null>(null);
  const key = `${kind}:${label ?? ""}`;

  useEffect(() => {
    let cancelled = false;
    let handle: { skip(): void } | null = null;
    const n = ++runSeq;
    const go = async () => {
      if (kind === "vs") {
        const id = `O16:vs:${n}`;
        setRun({ id, stage: "vs" });
        const sting = window.setTimeout(() => audio.playSfx("vs_sting"), 350);
        const h = playCeremony(id, { durationMs: VS_MS, onSkip: () => clearTimeout(sting) });
        handle = h;
        const r = await h.done;
        clearTimeout(sting);
        if (cancelled) return;
        if (r === "skipped" || !label) return close();
      }
      if (!label) return close();
      const id = `O16:round:${n}`;
      setRun({ id, stage: "round" });
      const gong = window.setTimeout(() => audio.playSfx("round_gong"), 160);
      const h = playCeremony(id, { durationMs: BANNER_MS, onSkip: () => clearTimeout(gong) });
      handle = h;
      await h.done;
      clearTimeout(gong);
      if (!cancelled) close();
    };
    // Deferred one tick so StrictMode's mount→unmount→mount never queues a phantom ceremony.
    const start = window.setTimeout(() => void go(), 0);
    return () => {
      cancelled = true;
      clearTimeout(start);
      handle?.skip();
    };
    // Re-run only when the request itself changes (a newer boundary replaces the props).
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!run) return null;
  return run.stage === "vs"
    ? <VsView key={run.id} id={run.id} sessionId={sessionId} />
    : <BannerView key={run.id} id={run.id} label={label ?? ""} />;
}

/** `show` stays false while the ceremony waits in the conductor queue, so nothing animates early. */
function useEnd(id: string): { show: boolean; end: boolean; skipped: boolean } {
  const { active, skipped } = useCeremony(id);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    if (active) setSeen(true);
  }, [active]);
  return { show: active || seen, end: skipped || (seen && !active), skipped };
}

function VsView({ id, sessionId }: { id: string; sessionId: string }) {
  const { show, end, skipped } = useEnd(id);
  const { reduced } = useMotionPrefs();
  const slot = useSlot(sessionId);
  const chars = useCharMap();
  const session = slot?.runtime?.session;
  const cfg = (session?.config ?? null) as DebateConfig | null;
  const cols = useMemo(() => debateColumns(session?.participants ?? [], cfg), [session?.participants, cfg]);
  const panel = cfg?.format === "panel";
  const emo = (cid: string) => slot?.runtime?.displayEmotion[cid] ?? "neutral";

  const stack = (side: "prop" | "opp") => (
    <div className={cx(s.stack, s[`stack_${side}`])}>
      {cols[side].map((cid, i) => {
        const c = chars[cid];
        if (!c) return null;
        return (
          <div key={cid} className={s.fly} style={{ "--i": i, "--n": cols[side].length } as CSSProperties}>
            <PortraitCard character={c} emotion={emo(cid)} size="stage" width="var(--vs-card)" parallax={false} showPlate />
          </div>
        );
      })}
    </div>
  );

  if (!show) return null;
  return (
    <div className={cx(s.vs, reduced && s.reduced)} data-end={end || undefined} data-skipped={skipped || undefined} aria-hidden="true">
      <div className={cx(s.half, s.halfProp)} />
      <div className={cx(s.half, s.halfOpp)} />
      <div className={s.seam} />
      {stack("prop")}
      {stack("opp")}
      <div className={s.sideLabels}>
        <Tape tone="ink" size="lg" rotate={-4}>{panel ? "Panel" : "Proposition"}</Tape>
        <Tape tone="ink" size="lg" rotate={4}>{panel ? "Panel" : "Opposition"}</Tape>
      </div>
      <div className={s.vsMark}>
        <RansomText text={panel ? "PANEL" : "VS"} size={panel ? 96 : 168} tone="mixed" />
      </div>
      {cfg?.motion && (
        <div className={s.motionTape}>
          <span className={s.motionKicker}>Motion</span>
          <span className={s.motionText} style={{ "--chars": Math.min(cfg.motion.length, 120) } as CSSProperties}>{cfg.motion}</span>
        </div>
      )}
      <span className="sr-only">Debate starts</span>
    </div>
  );
}

function BannerView({ id, label }: { id: string; label: string }) {
  const { show, end } = useEnd(id);
  const { reduced } = useMotionPrefs();
  if (!show) return null;
  const [round, ...rest] = label.split(":");
  const title = rest.join(":").trim();
  return (
    <div className={cx(s.bannerWrap, reduced && s.reduced)} data-end={end || undefined} role="status" aria-live="polite">
      <div className={s.bannerTape}>
        <span className={s.bannerStripe} aria-hidden="true" />
        {title ? (
          <>
            <span className={s.roundKicker}>{round}</span>
            <RansomText key={end ? "e" : "p"} text={title} size={64} tone="mixed" slam={!end} delayMs={180} staggerMs={40} />
          </>
        ) : (
          <RansomText key={end ? "e" : "p"} text={label} size={72} tone="mixed" slam={!end} delayMs={180} staggerMs={40} />
        )}
      </div>
    </div>
  );
}
