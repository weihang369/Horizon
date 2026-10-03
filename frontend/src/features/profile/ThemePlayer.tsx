// Theme song player (CHR-10 AC3, PRF-04): waveform from the decoded buffer, ▶/❚❚ on the music bus, loop region,
// "SKETCH" for procedural placeholders (R11), model + licence small print. Owner: Builder B.
import { useSyncExternalStore } from "react";
import type { CSSProperties } from "react";
import { audio } from "@/audio/engine";
import type { ThemeSong } from "@/contract/types";
import { PauseIcon, PlayIcon, Tape } from "@/ui";
import { cx } from "@/ui/cx";
import { BARS, fakePeaks, usePeaks } from "./peaks";
import s from "./ThemePlayer.module.css";

export function useAudioState() {
  return useSyncExternalStore((cb) => audio.subscribe(cb), () => audio.getState(), () => audio.getState());
}

export function themeLabel(name: string): string {
  return `${name.split(" ")[0]}'s Theme`;
}

export interface ThemePlayerProps {
  song: ThemeSong;
  characterName: string;
  compact?: boolean;
  className?: string;
}

export function ThemePlayer({ song, characterName, compact, className }: ThemePlayerProps) {
  const st = useAudioState();
  const peaks = usePeaks(song.url);
  const playing = !!song.url && st.track?.url === song.url;
  const label = themeLabel(characterName);
  const procedural = !!song.url && (/\.proc\.json(\?|#|$)/.test(song.url) || song.url.startsWith("placeholder:"));
  const dur = song.durationSec ?? 16;
  const loop = song.loop;
  const toggle = () => {
    if (!song.url) return;
    if (playing) audio.setMusic(null, { crossfadeMs: 400 });
    else audio.setMusic(song.url, { label, crossfadeMs: 600, gainDb: song.gainDb });
  };
  return (
    <div className={cx(s.player, compact && s.compact, playing && s.playing, className)}>
      <button type="button" className={s.play} onClick={toggle} aria-pressed={playing} aria-label={playing ? `Pause ${label}` : `Play ${label}`}>
        {playing ? <PauseIcon width={22} height={22} /> : <PlayIcon width={22} height={22} />}
      </button>
      <div className={s.meta}>
        <div className={s.titleRow}>
          <span className={s.title}>{label}</span>
          {procedural && <Tape tone="ink" size="sm">Sketch</Tape>}
          {st.loading && playing && <span className={s.loading}>loading…</span>}
        </div>
        <div className={s.wave} style={{ "--dur": `${dur}s` } as CSSProperties} aria-hidden="true">
          {loop && <span className={s.loop} style={{ left: `${(loop.startSec / dur) * 100}%`, width: `${((loop.endSec - loop.startSec) / dur) * 100}%` }} />}
          {peaks.map((p, i) => <i key={i} style={{ transform: `scaleY(${p})` }} />)}
          {playing && <span className={s.head} />}
        </div>
        {!compact && (
          <div className={s.small}>
            <span>{song.brief.genres.join(" · ")} · {song.brief.bpm} BPM · {dur.toFixed(0)} s loop</span>
            <span>{song.generation?.model ?? "model n/a"} · {song.licenseNote}</span>
          </div>
        )}
      </div>
    </div>
  );
}

/** Spinning vinyl + waveform skeleton (STATE-02 "Song composing"). */
export function Composing({ progress, label = "Composing…" }: { progress: number; label?: string }) {
  return (
    <div className={s.composing} role="status" aria-label={`${label} ${Math.round(progress * 100)} %`}>
      <span className={s.vinyl} aria-hidden="true"><i /></span>
      <div className={s.meta}>
        <div className={s.titleRow}><span className={s.title}>{label}</span><span className={s.pct}>{Math.round(progress * 100)} %</span></div>
        <div className={cx(s.wave, s.waveSkel)} aria-hidden="true">
          {fakePeaks("composing").map((p, i) => <i key={i} style={{ transform: `scaleY(${p})`, opacity: i / BARS < progress ? 1 : 0.25 }} />)}
        </div>
        <div className={s.small}><span>Runs in the background. Keep going; we'll ping you when it lands.</span></div>
      </div>
    </div>
  );
}
