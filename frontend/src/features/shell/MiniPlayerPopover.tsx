// O09 Mini-player popover (MUS-04, R11): now playing, SKETCH explainer, master/music/SFX volume + mutes.
// Changes go through the prefs store, which drives the audio engine live. Owner: Builder A.
import { useSyncExternalStore } from "react";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { audio } from "../../audio/engine";
import { getRoute, navigate } from "../../router";
import { formatRoute } from "../../router/routes";
import { setPrefs, usePrefs } from "../../stores/prefs";
import { Slider, Toggle } from "../../ui/Controls";
import { Tape } from "../../ui/Tape";
import { trackLabel } from "./MiniPlayer";
import s from "./Overlays.module.css";

const pct = (v: number) => `${Math.round(v * 100)} %`;

export function MiniPlayerPopover({ close }: OverlayComponentProps<"O09">) {
  const st = useSyncExternalStore((cb) => audio.subscribe(cb), () => audio.getState());
  const a = usePrefs((p) => p.audio);
  return (
    <div className={s.pop} role="dialog" aria-label="Music and volume">
      <div className={s.popHead}>
        <Tape tone="brand" size="sm">NOW PLAYING</Tape>
        <p className={s.popTrack}>{trackLabel(st)}</p>
        {st.track?.procedural && (
          <p className={s.popSketch}>
            <span className={s.sketchTag}>SKETCH</span>
            A procedural placeholder rendered in your browser. Real music swaps in by URL.
          </p>
        )}
      </div>
      <div className={s.popBody}>
        <Slider label="Master" value={a.master} min={0} max={1} step={0.05} format={pct} onChange={(master) => setPrefs({ audio: { master, masterMuted: false } })} />
        <Slider label="Music" value={a.music} min={0} max={1} step={0.05} format={pct} onChange={(music) => setPrefs({ audio: { music, musicMuted: false } })} />
        <Slider label="Sound effects" value={a.sfx} min={0} max={1} step={0.05} format={pct} onChange={(sfx) => setPrefs({ audio: { sfx, sfxMuted: false } })} />
        <div className={s.popToggles}>
          <Toggle label="Mute all" checked={a.masterMuted} onChange={(masterMuted) => setPrefs({ audio: { masterMuted } })} />
          <Toggle label="Mute music" checked={a.musicMuted} onChange={(musicMuted) => setPrefs({ audio: { musicMuted } })} />
        </div>
      </div>
      <button
        type="button"
        className={s.popLink}
        onClick={() => {
          close();
          navigate({ name: "settings", tab: "audio", from: formatRoute(getRoute()) });
        }}
      >
        Audio settings ▸
      </button>
    </div>
  );
}
