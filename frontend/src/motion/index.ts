// Motion: transitions, ceremonies (conductor), display prefs, tokens. Owner: VMD.
export { runTransition, registerTransitionHost, shardPolygons, type TransitionKind, type TransitionOpts, type TransitionHandle } from "./transitions";
export { TransitionLayer } from "./TransitionLayer";
export {
  playCeremony, useCeremony, skipAllCeremonies, isCeremonyActive, getCeremonyState, subscribeCeremonies,
  type CeremonyHandle, type CeremonyOpts, type CeremonyResult, type CeremonyState,
} from "./conductor";
export {
  applyDisplayPrefs, getMotionPrefs, useMotionPrefs, effectiveVfx, subscribeMotionPrefs,
  type DisplayPrefs, type MotionPrefs, type VfxIntensity, type FlashIntensity,
} from "./prefs";
export { DUR, EASE, STAGGER, FLASH_PEAK, FLOOD_MIN_GAP_MS } from "./tokens";
