// Procedural "SKETCH" audio (R11, D-52). Owner: VMD.
// spec/prng are pure (Node-safe, used by the seed build); the renderers need WebAudio.
export * from "./spec";
export { makeRng, hashString, type Rng } from "./prng";
export { renderTheme } from "./renderTheme";
export { renderSfx, SFX_IDS, SFX_DUCKS, isSfxId, type SfxId } from "./sfx";
export { renderSystemTrack, SYSTEM_TRACK_KINDS, isSystemTrackKind } from "./system";
