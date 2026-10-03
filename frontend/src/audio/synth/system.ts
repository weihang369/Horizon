// System tracks (VMD paper §2.6): Main 100 BPM Dorian · Arena 128 BPM Phrygian · Bed 60 BPM Lydian pad.
// Rendered from SYSTEM_TRACK_SPECS through the same theme renderer. Owner: VMD. Browser only.
import { renderTheme } from "./renderTheme";
import { SYSTEM_TRACK_SPECS, type SystemTrackKind } from "./spec";

export const SYSTEM_TRACK_KINDS: SystemTrackKind[] = ["main_theme", "arena", "ambient_bed"];

export function isSystemTrackKind(x: string): x is SystemTrackKind {
  return (SYSTEM_TRACK_KINDS as string[]).includes(x);
}

export function renderSystemTrack(kind: SystemTrackKind): Promise<AudioBuffer> {
  return renderTheme(SYSTEM_TRACK_SPECS[kind]);
}
