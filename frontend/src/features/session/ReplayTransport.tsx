// O23 Replay transport (UXA §2.3, MULTI-15, R16): ❚❚/▶ · scrubber with event markers · ×1/×2/×4 · gap-trim
// toggle · Continue live ▸ (forks the seed at the playhead, D-51). Space = play/pause, ←/→ = previous/next turn.
// The REPLAY badge is drawn by the SessionScreen frame (top-left of the stage).
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { useStore } from "zustand";
import { createStore } from "zustand/vanilla";
import { client } from "../../client";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { openOverlay, toast } from "../../app/layers";
import { run } from "../../app/errors";
import { useShortcut } from "../../app/shortcuts";
import type { SessionEvent } from "../../contract/types";
import { navigate } from "../../router";
import { prefs, setPrefs, usePrefs } from "../../stores/prefs";
import { entities } from "../../stores/entities";
import { Tooltip } from "../../ui/Data";
import { cx } from "../../ui/cx";
import { ChevronRightIcon, KeyIcon, PauseIcon, PlayIcon } from "../../ui/icons";
import { formatClock, replayMarkers, stepTurn, type ReplayMarker } from "./replayMarkers";
import { firstName, useSessionCtx } from "./sessionContext";
import type { DockProps } from "./registry";
import s from "./ReplayTransport.module.css";

/** Ask the frame to rebuild the replay runtime (gap trim changed) and come back to `seq`. */
export const retimeBus = createStore<{ n: number; seq: number }>(() => ({ n: 0, seq: 0 }));

const RATES = [1, 2, 4] as const;
const eventsCache = new Map<string, Promise<SessionEvent[]>>();

/** "Continue live" (R16): fork the recording at the playhead (whole recording with no playhead). */
export async function continueLive(sessionId: string, worldId: string, title: string, atSeq: number | undefined, demo: boolean): Promise<void> {
  if (demo) {
    openOverlay("O05", { reason: "Continuing a recording live needs your OpenRouter key." });
    return;
  }
  const snap = await run(() => client.sessions.forkSeedSession(sessionId, atSeq));
  if (!snap) return;
  navigate({ name: "session", worldId, sessionId: snap.session.id }, { transition: "slash" });
  toast({ variant: "success", text: `Live copy of “${title}”${atSeq ? " from the playhead" : ""}.` });
}

/** Playhead for the scrubber: follows the player (rAF while playing); `set` writes a seek through at once so the
 * controlled range never re-renders the stale value (the native `change` that follows `input` would seek back). */
function useLivePosition(rt: DockProps["rt"]): [number, (ms: number) => void] {
  const p = rt.player;
  const [pos, setPos] = useState(p?.position ?? 0);
  const playing = !!p?.playing;
  useEffect(() => {
    setPos(rt.controls.position());
    if (!playing) return;
    let raf = 0;
    const tick = () => {
      setPos(rt.controls.position());
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, p?.position, rt.controls]);
  return [pos, setPos];
}

export function ReplayDock({ rt, sessionId, worldId }: DockProps) {
  const ctx = useSessionCtx();
  const p = rt.player;
  const duration = p?.duration ?? 0;
  const [pos, setLivePos] = useLivePosition(rt);
  const trim = usePrefs((x) => x.replayTrimGaps);
  const chars = useStore(entities, (st) => st.chars);
  const [events, setEvents] = useState<SessionEvent[] | null>(null);
  const playBtn = useRef<HTMLButtonElement>(null);
  const session = rt.session;
  const demo = ctx?.demo ?? true;

  useEffect(() => {
    let alive = true;
    let pr = eventsCache.get(sessionId);
    if (!pr) {
      pr = client.sessions.events(sessionId);
      eventsCache.set(sessionId, pr);
    }
    pr.then((e) => alive && setEvents(e), () => eventsCache.delete(sessionId));
    return () => { alive = false; };
  }, [sessionId]);

  // Replays open with focus on ▶ (UXA §2.4).
  useEffect(() => {
    playBtn.current?.focus({ preventScroll: true });
  }, []);

  const markers = useMemo<ReplayMarker[]>(
    () => (events ? replayMarkers(events, trim, (id) => firstName(chars[id]?.profile.name) || "") : []),
    [events, trim, chars],
  );

  const toggle = () => (p?.playing ? rt.controls.pause() : rt.controls.play());
  const seekTo = (ms: number) => {
    const t = Math.max(0, Math.min(ms, duration));
    setLivePos(t);
    rt.controls.seek(t);
  };
  const step = (dir: 1 | -1) => {
    const t = stepTurn(markers, rt.controls.position(), dir);
    if (t !== null) seekTo(t);
  };
  useShortcut("space", (e) => {
    e.preventDefault();
    toggle();
  });
  useShortcut("arrowright", () => step(1));
  useShortcut("arrowleft", () => step(-1));

  const seq = p?.seq ?? 0;
  const atSeq = p && seq > 0 && !p.ended && pos > 60 ? seq : undefined;
  const pct = duration ? Math.min(1, pos / duration) : 0;
  const isSeed = !!session?.isSeed;

  const retime = () => {
    const was = prefs.getState().replayTrimGaps;
    setPrefs({ replayTrimGaps: !was });
    retimeBus.setState((st) => ({ n: st.n + 1, seq }));
  };

  return (
    <div className={s.dock} role="group" aria-label="Replay transport">
      <button
        ref={playBtn}
        type="button"
        className={cx(s.play, p?.playing && s.playing)}
        onClick={toggle}
        aria-label={p?.playing ? "Pause replay (Space)" : p?.ended ? "Replay from the start (Space)" : "Play replay (Space)"}
      >
        <span className={s.playShape} aria-hidden="true" />
        <span className={s.playIcon}>{p?.playing ? <PauseIcon width={20} height={20} /> : <PlayIcon width={20} height={20} />}</span>
      </button>

      <div className={s.scrub}>
        <div className={s.time} aria-hidden="true">
          <span className={s.now}>{formatClock(pos)}</span>
          <span className={s.dur}>/ {formatClock(duration)}</span>
        </div>
        <div className={s.track} style={{ "--p": pct } as CSSProperties}>
          <span className={s.fill} />
          {duration > 0 && markers.map((m, i) => (
            <span
              key={i}
              className={cx(s.mark, s[`mark_${m.kind}`], m.t <= pos && s.markPast)}
              style={{ left: `${(m.t / duration) * 100}%` }}
              title={m.label}
            >
              {m.kind === "round" && <span className={s.markLabel}>{m.label.replace(/^ROUND /i, "R").replace(/ · .*/, "")}</span>}
            </span>
          ))}
          <span className={s.head} />
          <input
            type="range"
            className={s.range}
            min={0}
            max={Math.max(1, Math.round(duration))}
            step={1}
            value={Math.round(pos)}
            aria-label="Seek"
            aria-valuetext={`${formatClock(pos)} of ${formatClock(duration)}`}
            onChange={(e) => seekTo(Number(e.target.value))}
            onKeyDown={(e) => {
              // The keyboard drives the playhead here (not the native range): ←/→ step by turn like the global
              // shortcut, Home/End hit the true ends, PgUp/PgDn jump 10 s. preventDefault keeps the global handler out.
              const k = e.key;
              if (k === " ") toggle();
              else if (k === "ArrowRight" || k === "ArrowUp") step(1);
              else if (k === "ArrowLeft" || k === "ArrowDown") step(-1);
              else if (k === "Home") seekTo(0);
              else if (k === "End") seekTo(duration);
              else if (k === "PageUp") seekTo(rt.controls.position() + 10_000);
              else if (k === "PageDown") seekTo(rt.controls.position() - 10_000);
              else return;
              e.preventDefault();
            }}
          />
        </div>
        <ul className={s.legend} aria-hidden="true">
          <li><i className={s.lgRound} />Round</li>
          <li><i className={s.lgTurn} />Turn</li>
          <li><i className={s.lgEmotion} />Emotion</li>
          {markers.some((m) => m.kind === "steer") && <li><i className={s.lgSteer} />Steer</li>}
        </ul>
      </div>

      <div className={s.rates} role="radiogroup" aria-label="Playback speed">
        {RATES.map((r) => (
          <button key={r} type="button" role="radio" aria-checked={(p?.rate ?? 1) === r} className={cx(s.rate, (p?.rate ?? 1) === r && s.rateOn)} onClick={() => rt.controls.rate(r)}>
            ×{r}
          </button>
        ))}
      </div>

      <Tooltip content={trim ? "Long pauses are trimmed to 2.5 s" : "Original pacing, pauses kept"}>
        <button type="button" className={cx(s.trim, trim && s.trimOn)} aria-pressed={trim} onClick={retime}>
          <span className={s.trimBox} aria-hidden="true" />Trim gaps
        </button>
      </Tooltip>

      {isSeed ? (
        <button
          type="button"
          className={s.cont}
          data-key-locked={demo || undefined}
          onClick={() => void continueLive(sessionId, worldId, session?.title ?? "", atSeq, demo)}
          aria-label={`Continue live${atSeq ? " from the playhead" : ""}${demo ? " (needs API key)" : ""}`}
        >
          <span className={s.contShape} aria-hidden="true" />
          <span className={s.contContent}>
            {demo && <KeyIcon width={14} height={14} />}
            <span className={s.contText}>
              Continue live
              <small>{atSeq ? `from ${formatClock(pos)}` : "whole recording"}</small>
            </span>
            <ChevronRightIcon width={16} height={16} />
          </span>
        </button>
      ) : (
        <button type="button" className={s.cont} onClick={() => navigate({ name: "session", worldId, sessionId })}>
          <span className={s.contShape} aria-hidden="true" />
          <span className={s.contContent}><span className={s.contText}>Back to live<small>exit replay</small></span><ChevronRightIcon width={16} height={16} /></span>
        </button>
      )}
    </div>
  );
}

/** O23 registry entry (ambient: it renders inside the session dock, not on the LayerStack). */
export function ReplayTransport(_: Partial<OverlayComponentProps<"O23">>) {
  return null;
}
