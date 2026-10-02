// S01 Title (APP-01, R18): fonts (≤ 800 ms) → kinetic RansomText intro → "Press any key".
// The first gesture unlocks audio, starts the main theme and slashes to Onboarding (first run, no key) or World Select.
// This is the first frame of the showreel: retro sun, ransom tiles, a −12° band and ink shards. Owner: Builder A.
import { useEffect, useRef, useState } from "react";
import { audio } from "../../audio/engine";
import { useSettings } from "../../client/hooks";
import { useMotionPrefs } from "../../motion/prefs";
import { navigate } from "../../router";
import { prefs } from "../../stores/prefs";
import { ui } from "../../stores/ui";
import { waitForFonts } from "../../styles/fonts";
import { RansomText } from "../../ui/RansomText";
import { playMainTheme, useHouseScreen } from "./house";
import s from "./Title.module.css";

const IGNORED_KEYS = new Set(["Shift", "Control", "Alt", "Meta", "Tab", "CapsLock", "Fn", "OS", "ContextMenu", "Escape"]);
export const APP_VERSION = "v0.1 · UI PREVIEW";

export function TitleScreen() {
  useHouseScreen({ music: false });
  const settings = useSettings().data;
  const settingsRef = useRef(settings);
  settingsRef.current = settings;
  const { reduced } = useMotionPrefs();
  const [ready, setReady] = useState(false);
  const [going, setGoing] = useState(false);
  const gone = useRef(false);

  useEffect(() => {
    let alive = true;
    void waitForFonts(800).then(() => alive && setReady(true));
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    const go = () => {
      if (gone.current) return;
      gone.current = true;
      setGoing(true);
      void audio.unlock().then(() => {
        playMainTheme();
        audio.playSfx("ui_confirm");
      });
      const firstRun = !prefs.getState().seenOnboarding && settingsRef.current?.openRouterKeyStatus !== "set";
      window.setTimeout(() => navigate(firstRun ? { name: "onboarding", card: 1 } : { name: "worlds" }), reduced ? 0 : 160);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.altKey || e.metaKey || IGNORED_KEYS.has(e.key) || e.repeat) return;
      if (ui.getState().layers.length) return;
      go();
    };
    const onPointer = (e: PointerEvent) => {
      if (e.button !== 0 || ui.getState().layers.length) return;
      if ((e.target as Element | null)?.closest?.("[data-layer],[data-dev]")) return;
      go();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onPointer);
    };
  }, [reduced]);

  return (
    <main className={s.title} data-screen="S01" data-ready={ready || undefined} data-going={going || undefined}>
      <div className={s.sky} aria-hidden="true" />
      <div className={s.halftone} aria-hidden="true" />
      <div className={s.ghost} aria-hidden="true">
        <span>HORIZON HORIZON HORIZON </span>
        <span>HORIZON HORIZON HORIZON </span>
      </div>
      <div className={s.sunWrap} aria-hidden="true">
        <div className={s.sun} />
      </div>
      <div className={s.sea} aria-hidden="true" />
      <div className={s.band} aria-hidden="true" />
      <div className={s.bandInk} aria-hidden="true" />
      <div className={`${s.shard} ${s.shardA}`} aria-hidden="true" />
      <div className={`${s.shard} ${s.shardB}`} aria-hidden="true" />
      <div className={`${s.shard} ${s.shardC}`} aria-hidden="true" />

      <div className={s.center}>
        {ready ? (
          <h1 className={s.logo}>
            <RansomText text="HORIZON" as="span" size="var(--logo-size)" tone="mixed" slam delayMs={150} staggerMs={60} />
          </h1>
        ) : (
          <h1 className={s.logoPlaceholder}>Horizon</h1>
        )}
        <p className={s.sub}>
          <span className={s.subText}>Summon characters · Watch them think · Let them argue</span>
        </p>
        <button type="button" className={s.press} onClick={(e) => e.preventDefault()} aria-label="Press any key to start">
          <span className={s.pressFill} aria-hidden="true" />
          <span className={s.pressText}>Press any key</span>
          <span className={s.pressCaret} aria-hidden="true">▸</span>
        </button>
      </div>

      <footer className={s.foot}>
        <span className={s.footTag}>Open source · Bring your own OpenRouter key</span>
        <span className={s.version}>{APP_VERSION}</span>
      </footer>
    </main>
  );
}
