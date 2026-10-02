// House-palette screens (Title, Onboarding, Worlds, Hub, Settings): snap the app root back to the house palette on
// entry so a palette left by a profile or 1:1 never leaks in (R9), and keep the system main theme playing (MUS-05).
// Owner: Builder A.
import { useEffect } from "react";
import tracks from "@seed/system-tracks.json";
import { audio } from "../../audio/engine";
import { setAppPalette } from "../../theme/appPalette";

type TrackKind = "main_theme" | "arena" | "ambient_bed";
const TRACKS = (tracks as { data: { kind: TrackKind; url: string }[] }).data;

/** A system track URL from the seed catalogue (swapping to real audio is a URL change only, R11). */
export function systemTrackUrl(kind: TrackKind): string {
  return TRACKS.find((t) => t.kind === kind)?.url ?? `placeholder:system/${kind}`;
}

export const MAIN_THEME_LABEL = "Horizon Main Theme";

/** Start (or keep) the main theme. Same URL = no restart (MUS-02). Before unlock it is queued by the engine. */
export function playMainTheme(): void {
  audio.setMusic(systemTrackUrl("main_theme"), { label: MAIN_THEME_LABEL, crossfadeMs: 1500 });
}

/** Call once per house screen. `music: false` leaves whatever is playing (Settings, Title before the gesture). */
export function useHouseScreen(opts: { music?: boolean } = {}): void {
  const music = opts.music ?? true;
  useEffect(() => {
    setAppPalette(null);
    if (music) playMainTheme();
    // A palette flood started just before leaving (profile / wizard) flips the root class at its cover point,
    // which can land after this mount: snap back once more after the longest flood.
    const t = window.setTimeout(() => setAppPalette(null), 900);
    return () => window.clearTimeout(t);
  }, [music]);
}
