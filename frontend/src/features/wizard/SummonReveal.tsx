// O15 Summon reveal (CHR-11 AC2, VMD §2.4 "Summon (1800)"): the wizard's climax. Owner: Builder B.
//   0     palette flood (setAppPalette, R10) + ink stage
//   350   slash band sweeps
//   500   portrait slides in from +40vw (380 ms) with three ghost copies collapsing as motion blur
//   900   name tiles slam, then the card shakes
//   1150  tagline types (28 ms/char)
//   1200  summon sting + the theme fades in (ambient bed while the song is still composing, AC2b)
//   ~     a giant outlined "SUMMONED" drifts behind at 6 %
// Runs through playCeremony, so any key/click skips to the end state (R6, D-55) and the input still lands on the
// profile underneath (the layer is pointer-events:none). Reduced motion → a ≤ 200 ms fade.
import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { audio } from "@/audio/engine";
import type { OverlayComponentProps } from "@/app/overlayTypes";
import { toast } from "@/app/layers";
import { client } from "@/client";
import { useCharacter, useSong } from "@/client/hooks";
import { PortraitCard } from "@/character";
import { playCeremony, useMotionPrefs } from "@/motion";
import { getPalette, PaletteScope, setAppPalette } from "@/theme";
import { RansomText } from "@/ui";
import { cx } from "@/ui/cx";
import { themeLabel } from "@/features/profile/ThemePlayer";
import s from "./summon.module.css";

const CEREMONY_MS = 2600;
const STING_AT = 1200;
const REDUCED_HOLD_MS = 1200;

/** Resolves after `ms`, or on the first key or pointer press (observed only, never cancelled). */
function holdUnlessInput(ms: number): Promise<void> {
  return new Promise((res) => {
    const done = () => {
      clearTimeout(t);
      window.removeEventListener("keydown", done);
      window.removeEventListener("pointerdown", done);
      res();
    };
    const t = window.setTimeout(done, ms);
    window.addEventListener("keydown", done);
    window.addEventListener("pointerdown", done);
  });
}
const TYPE_AT = 1150;
const TYPE_MS = 28;
const AMBIENT = "placeholder:system/ambient_bed";

/** CHR-11 AC2b: when the theme finishes composing after the summon, ping once. */
const watching = new Set<string>();
function watchSong(characterId: string, name: string): void {
  if (watching.has(characterId)) return;
  watching.add(characterId);
  void client.jobs.listActive().then((jobs) => {
    const j = jobs.find((x) => x.characterId === characterId && x.kind === "song");
    if (!j) return void watching.delete(characterId);
    const off = client.jobs.subscribe(j.id, (e) => {
      if (e.type !== "job.done") return;
      off();
      watching.delete(characterId);
      if (e.job.status !== "succeeded") return;
      void client.characters.song(characterId).then((song) => {
        if (!song?.url) return;
        toast({ variant: "success", text: `${name}'s theme is ready ▶`, action: { label: "Play", run: () => audio.setMusic(song.url!, { label: themeLabel(name) }) } });
      });
    });
  });
}

export function SummonReveal({ close, characterId }: OverlayComponentProps<"O15">) {
  const c = useCharacter(characterId).data;
  const song = useSong(characterId).data;
  const prefs = useMotionPrefs();
  const [phase, setPhase] = useState<"play" | "skipped" | "leaving">("play");
  const [typed, setTyped] = useState(0);
  const started = useRef(false);
  const musicStarted = useRef(false);
  const latest = useRef({ c, song });
  latest.current = { c, song };

  const startMusic = () => {
    if (musicStarted.current) return;
    musicStarted.current = true;
    const { c: ch, song: sg } = latest.current;
    const name = ch?.profile.name ?? "Their";
    if (sg?.status === "ready" && sg.url) audio.setMusic(sg.url, { label: themeLabel(name), crossfadeMs: 900, gainDb: sg.gainDb });
    else {
      audio.setMusic(AMBIENT, { label: "Ambient bed", crossfadeMs: 900 });
      watchSong(characterId, name);
    }
  };

  // Kick off once the character is known (palette + name needed).
  useEffect(() => {
    if (!c || started.current) return;
    started.current = true;
    const flood = { x: window.innerWidth - 170, y: window.innerHeight - 40 };
    setAppPalette(null);
    setAppPalette(c.paletteId, { flood });
    audio.playSfx("ui_flood");
    const timers: number[] = [];
    timers.push(window.setTimeout(() => audio.playSfx("ui_whoosh"), 350));
    timers.push(window.setTimeout(() => {
      audio.duck();
      audio.playSfx("summon_sting");
      startMusic();
    }, prefs.reduced ? 0 : STING_AT));
    const h = playCeremony("summon", {
      durationMs: CEREMONY_MS,
      onSkip: () => {
        timers.forEach(clearTimeout);
        setPhase("skipped");
        setTyped(Infinity);
        startMusic();
      },
    });
    void h.done.then(async (r) => {
      // Reduced motion: the end card holds still for a readable beat (same rule as the VS banner); any key or click
      // ends it early, and the listeners never preventDefault, so input still reaches the profile (R6).
      if (prefs.reduced && r !== "skipped") await holdUnlessInput(REDUCED_HOLD_MS);
      setPhase("leaving");
      window.setTimeout(close, r === "skipped" || prefs.reduced ? 140 : 380);
    });
    // No timer cleanup: StrictMode's simulated unmount would drop the sting; onSkip clears them instead.
  }, [c]); // eslint-disable-line react-hooks/exhaustive-deps

  // Tagline typewriter.
  const tagline = c?.profile.tagline ?? "";
  useEffect(() => {
    if (!c || phase !== "play" || prefs.reduced) return void setTyped(Infinity);
    let i = 0;
    let t = 0;
    const start = window.setTimeout(() => {
      t = window.setInterval(() => {
        i += 1;
        setTyped(i);
        if (i >= tagline.length) window.clearInterval(t);
      }, TYPE_MS);
    }, TYPE_AT);
    return () => {
      window.clearTimeout(start);
      window.clearInterval(t);
    };
  }, [c?.id, phase]); // eslint-disable-line react-hooks/exhaustive-deps

  const pal = useMemo(() => getPalette(c?.paletteId), [c?.paletteId]);
  if (!c) return null;
  const first = c.profile.name.split(" ")[0] || c.profile.name;
  const rest = c.profile.name.slice(first.length).trim();

  return (
    <PaletteScope
      paletteId={c.paletteId}
      className={cx(s.root, phase === "skipped" && s.skip, phase === "leaving" && s.leaving, prefs.reduced && s.reduced)}
      aria-live="polite"
      style={{ "--pal-name": `"${pal.name}"` } as CSSProperties}
    >
      <span className="sr-only">{c.profile.name} summoned.</span>
      <div className={s.stage} aria-hidden="true">
        <span className={s.halftone} />
        <span className={s.word}>SUMMONED</span>
        <span className={s.slash} />
        <span className={s.band} />
        <span className={s.rays} />
        <span className={s.panel} />
      </div>
      <div className={s.portraitWrap} aria-hidden="true">
        <span className={cx(s.ghost, s.g3)}><PortraitCard character={c} emotion="happy" size="hero" width="var(--sm-w)" parallax={false} /></span>
        <span className={cx(s.ghost, s.g2)}><PortraitCard character={c} emotion="happy" size="hero" width="var(--sm-w)" parallax={false} /></span>
        <span className={cx(s.ghost, s.g1)}><PortraitCard character={c} emotion="happy" size="hero" width="var(--sm-w)" parallax={false} /></span>
        <div className={s.portrait}>
          <PortraitCard character={c} emotion={c.emotions.happy ? "happy" : "neutral"} size="hero" width="var(--sm-w)" parallax={false} />
        </div>
      </div>
      <div className={s.copy} aria-hidden="true">
        <span className={s.kicker}>NEW CHARACTER · SUMMONED</span>
        <div className={s.name}>
          <RansomText text={first.toUpperCase()} size="var(--sm-name)" slam={!prefs.reduced} delayMs={900} staggerMs={45} tone="mixed" />
          {rest && <RansomText text={rest.toUpperCase()} size="calc(var(--sm-name) * 0.62)" slam={!prefs.reduced} delayMs={1050} staggerMs={35} tone="brand" />}
        </div>
        <span className={s.role}>{c.profile.title ? `${c.profile.title} · ` : ""}{c.profile.role}</span>
        {tagline && (
          <p className={s.tagline}>
            <span>“{tagline.slice(0, typed)}</span>
            {typed < tagline.length && <span className={s.caret} />}
            <span className={s.ghostText}>{tagline.slice(typed)}</span>
            <span className={typed < tagline.length ? s.ghostText : undefined}>”</span>
          </p>
        )}
        <span className={s.pal}><i />{pal.name}</span>
      </div>
      <span className={s.flash} aria-hidden="true" />
      <span className={s.skipHint} aria-hidden="true">ANY KEY · SKIP</span>
    </PaletteScope>
  );
}
