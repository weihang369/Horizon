// Mini-player chip (MUS-04/06/07, R11): skewed chip at the top right with a mini equaliser, the track name,
// "· SKETCH" for procedural tracks, and mute. Click → O09 volume popover. Driven by audio.getState/subscribe.
// Owner: Builder A. Statically imported by App (entry bundle): keep it light.
import { useSyncExternalStore } from "react";
import { openOverlay } from "../../app/layers";
import { audio } from "../../audio/engine";
import type { AudioState } from "../../audio/engine";
import { setPrefs, usePrefs } from "../../stores/prefs";
import s from "./MiniPlayer.module.css";

const subscribe = (cb: () => void) => audio.subscribe(cb);
const snapshot = () => audio.getState();

export function trackLabel(st: AudioState): string {
  if (st.blocked) return "Enable audio";
  if (!st.track) return "Silence";
  return st.track.label || "Untitled track";
}

export function MiniPlayer() {
  const st = useSyncExternalStore(subscribe, snapshot, snapshot);
  const muted = usePrefs((p) => p.audio.masterMuted || p.audio.musicMuted);
  const playing = st.unlocked && !!st.track && !st.loading && !muted;
  const label = trackLabel(st);

  if (st.blocked || !st.unlocked) {
    return (
      <div className={s.player} data-state="blocked">
        <button type="button" className={s.main} onClick={() => void audio.unlock()} aria-label="Enable audio">
          <span className={s.play} aria-hidden="true">▶</span>
          <span className={s.label}>{st.blocked ? "Enable audio" : st.track ? `♪ ${label}` : "Audio off"}</span>
          {st.track?.procedural && <span className={s.sketch}>SKETCH</span>}
        </button>
      </div>
    );
  }

  return (
    <div className={s.player} data-state={playing ? "playing" : "idle"}>
      <button
        type="button"
        className={s.main}
        aria-haspopup="dialog"
        aria-label={`Now playing: ${label}${st.track?.procedural ? ", procedural sketch" : ""}. Volume`}
        onClick={(e) => {
          const r = e.currentTarget.parentElement!.getBoundingClientRect();
          openOverlay("O09", { anchor: { x: Math.max(8, r.right - 330), y: r.y, width: r.width, height: r.height } });
        }}
      >
        <span className={s.eq} aria-hidden="true"><i /><i /><i /><i /></span>
        <span className={s.label}>{st.loading ? `♪ ${label}…` : `♪ ${label}`}</span>
        {st.track?.procedural && <span className={s.sketch} title="Procedural placeholder: real audio swaps in by URL">· SKETCH</span>}
      </button>
      <button
        type="button"
        className={s.mute}
        aria-pressed={muted}
        aria-label={muted ? "Unmute music" : "Mute music"}
        title={muted ? "Unmute" : "Mute"}
        onClick={() => setPrefs({ audio: { musicMuted: !muted, masterMuted: false } })}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M2.5 6h2.5l3.5-3v10L5 10H2.5z" />
          {muted ? <path d="M11 6l4 4M15 6l-4 4" /> : <path d="M11 5.5c1 .8 1.5 1.6 1.5 2.5s-.5 1.7-1.5 2.5M12.8 3.5C14.3 4.8 15 6.3 15 8s-.7 3.2-2.2 4.5" />}
        </svg>
      </button>
    </div>
  );
}
