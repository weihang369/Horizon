// VFX: Shadow Self placeholders, particles, emotion presets, covers, parallax, global ticker. Owner: VMD.
export * from "./shadow";
export * from "./particles";
export { playOneShot, startLoop, type CardBox, type VfxRun, type LoopPreset } from "./emotionPresets";
export { COVER_PRESETS, COVER_BY_ID, getCoverPreset, type CoverPreset, type CoverPresetId } from "./covers";
export { registerParallax } from "./parallax";
export { onTick, ticker, type TickFn } from "./ticker";
