// S06 Theme tab as a track page (CHR-12, PRF-04): sleeve + vinyl, big ▶/❚❚ on the music bus, the full waveform with
// its loop region, the brief as liner notes, credits, and the composing / failed / placeholder / none states.
// Uses only ThemeSong fields that exist. Owner: Builder B.
import type { CSSProperties } from "react";
import { audio } from "@/audio/engine";
import { useJob } from "@/client/hooks";
import type { Character, ThemeSong } from "@/contract/types";
import { Button, ErrorTape, PauseIcon, PlayIcon, Tape } from "@/ui";
import { formatUsd } from "@/ui";
import { cx } from "@/ui/cx";
import { isRunning, startGeneration, useCharacterJobs, useEstimate } from "@/features/wizard/generate";
import { BARS, fakePeaks, usePeaks } from "./peaks";
import { themeLabel, useAudioState } from "./ThemePlayer";
import s from "./ThemeTrack.module.css";

const mmss = (sec: number) => `${Math.floor(sec / 60)}:${String(Math.round(sec % 60)).padStart(2, "0")}`;
const isProcedural = (url?: string) => !!url && (/\.proc\.json(\?|#|$)/.test(url) || url.startsWith("placeholder:"));

type Phase = "ready" | "composing" | "failed" | "none";

export function ThemeTrack({ c, song }: { c: Character; song: ThemeSong | null }) {
  const first = c.profile.name.split(" ")[0];
  const label = themeLabel(c.profile.name);
  const jobs = useCharacterJobs(c.id);
  const job = useJob(jobs.song).data;
  const est = useEstimate({ characterId: c.id, kind: "song" });
  const st = useAudioState();
  const composing = isRunning(job) || song?.status === "generating";
  const ready = song?.status === "ready" && !!song.url;
  const jobFailed = !composing && job?.status === "failed";
  // A failed regenerate keeps the current theme: it stays "ready" with a failure tape.
  const phase: Phase = composing ? "composing" : ready ? "ready" : (jobFailed || song?.status === "failed") ? "failed" : "none";
  const stalled = phase === "failed" || (phase === "ready" && jobFailed);
  const peaks = usePeaks(ready ? song!.url : undefined);
  // Queued but silent until the browser lets audio start (first click or key): don't claim "Now playing" (QA-07).
  const queued = ready && st.track?.url === song!.url;
  const playing = queued && st.unlocked;
  const sketch = ready && isProcedural(song!.url);
  const dur = song?.durationSec ?? 16;
  const loop = song?.loop;
  const progress = composing ? job?.progress ?? 0 : 0;
  const archived = c.status === "archived";

  const toggle = () => {
    if (!ready) return;
    if (queued && !st.unlocked) void audio.unlock();
    else if (playing) audio.setMusic(null, { crossfadeMs: 400 });
    else audio.setMusic(song!.url!, { label, crossfadeMs: 600, gainDb: song!.gainDb });
  };
  const compose = () => void startGeneration(
    { characterId: c.id, kind: "song", ...(song?.brief ? { brief: song.brief } : {}) },
    ready ? "Regenerate theme" : "Compose theme",
  );
  const face = c.emotions.neutral?.url;
  const bars = phase === "ready" ? peaks : fakePeaks(phase === "composing" ? "composing" : c.id);

  return (
    <div className={cx(s.track, playing && s.playing, s[`ph_${phase}`])}>
      <div className={s.hero}>
        <div className={s.sleeveWrap}>
          <span className={s.disc} aria-hidden="true"><i /></span>
          <div className={s.sleeve} aria-hidden="true">
            {face && <img className={s.face} src={face} alt="" draggable={false} />}
            <span className={s.sleeveHalftone} />
            <span className={s.sleeveName}>{first}</span>
            <span className={s.sleeveNo}>Theme · 01</span>
            {phase === "failed" && <span className={s.stamp}>Stalled</span>}
            {phase === "none" && <span className={s.stamp}>Unreleased</span>}
          </div>
        </div>

        <div className={s.info}>
          <p className={s.kicker}>
            {phase === "composing" ? `Composing · ${Math.round(progress * 100)} %` : phase === "failed" ? "Track failed" : phase === "none" ? "No theme yet" : playing ? "Now playing" : "Character theme"}
          </p>
          <h3 className={s.title}>{label}</h3>
          <div className={s.tags}>
            {song?.brief && <span className={s.genre}>{song.brief.genres.join(" · ")}</span>}
            {sketch && <Tape tone="ink" size="sm">Sketch</Tape>}
            {song?.instrumental && <Tape tone="paper" size="sm">Instrumental</Tape>}
          </div>
          <div className={s.transport}>
            <button
              type="button"
              className={s.play}
              onClick={toggle}
              disabled={!ready}
              aria-pressed={playing}
              aria-label={playing ? `Pause ${label}` : `Play ${label}`}
            >
              {playing ? <PauseIcon width={30} height={30} /> : <PlayIcon width={30} height={30} />}
              <span>{playing ? "Pause" : "Play"}</span>
            </button>
            <dl className={s.stats}>
              {song?.brief && <div><dt>Tempo</dt><dd>{song.brief.bpm}<small> BPM</small></dd></div>}
              {ready && <div><dt>Length</dt><dd>{mmss(dur)}</dd></div>}
              {ready && loop && <div><dt>Loop</dt><dd>{mmss(loop.startSec)}–{mmss(loop.endSec)}</dd></div>}
              {ready && song?.gainDb !== undefined && <div><dt>Gain</dt><dd>{song.gainDb > 0 ? "+" : ""}{song.gainDb}<small> dB</small></dd></div>}
            </dl>
            {playing && st.loading && <span className={s.loading} role="status">loading…</span>}
            {queued && !st.unlocked && <span className={s.loading} role="status">Press Play to turn audio on</span>}
          </div>
        </div>
      </div>

      <div className={cx(s.wave, phase !== "ready" && s.waveSkel)} style={{ "--dur": `${dur}s` } as CSSProperties} aria-hidden="true">
        {phase === "ready" && loop && <span className={s.loopZone} style={{ left: `${(loop.startSec / dur) * 100}%`, width: `${((loop.endSec - loop.startSec) / dur) * 100}%` }}><b>Loop</b></span>}
        {bars.map((p, i) => <i key={i} style={{ transform: `scaleY(${p})`, ...(phase === "composing" ? { opacity: i / BARS < progress ? 1 : 0.22 } : {}) }} />)}
        {playing && phase === "ready" && <span className={s.head} />}
      </div>
      {phase === "ready" && <div className={s.ticks}><span>0:00</span><span>{song?.format?.toUpperCase() ?? (sketch ? "WebAudio sketch" : "")}</span><span>{mmss(dur)}</span></div>}

      {phase === "composing" && <p className={s.note} role="status">Runs in the background. Keep going; we'll ping you when {first}'s theme lands.</p>}
      {stalled && (
        <ErrorTape
          message={phase === "ready" ? `The new take stalled. ${first}'s current theme stays.` : "The composer stalled before the take was finished."}
          action={{ label: "Retry", run: compose, cost: est ?? undefined }}
        />
      )}
      {phase === "none" && <p className={s.note}>The ambient bed plays for {first} until a theme is composed.</p>}

      {song?.brief && (
        <section className={s.liner} aria-label="Liner notes">
          <h4 className={s.linerTitle}>Liner notes</h4>
          <blockquote className={s.vibe}>“{song.brief.vibe}”</blockquote>
          <dl className={s.linerList}>
            <div><dt>Genre</dt><dd>{song.brief.genres.join(", ")}</dd></div>
            <div><dt>Mood</dt><dd>{song.brief.moods.join(", ")}</dd></div>
            <div><dt>Instruments</dt><dd>{song.brief.instruments.join(", ")}</dd></div>
            <div><dt>Vocals</dt><dd>{song.instrumental ? "None (instrumental)" : "With vocals"}</dd></div>
          </dl>
          <p className={s.credits}>
            <span>Composed by {song.generation?.model ?? "google/lyria-3-clip"}</span>
            {song.generation?.costUsd !== undefined && <span>Cost {formatUsd(song.generation.costUsd)}</span>}
            <span>{song.licenseNote || (sketch ? "Placeholder: procedural WebAudio sketch (D-52)." : "")}</span>
          </p>
        </section>
      )}

      {!stalled && <div className={s.actions}>
        <Button variant={phase === "ready" ? "secondary" : "primary"} cost={est ?? undefined} disabled={composing || archived} onClick={compose}>
          {phase === "ready" ? "↻ Regenerate (replaces)" : "Compose ▸"}
        </Button>
        <span className={s.small}>One theme per character. Regenerating replaces it; there is no history.</span>
      </div>}
    </div>
  );
}
