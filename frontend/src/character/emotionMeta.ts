// emotionMeta (spec §3.5): label, glyph, MANUAL hotkey 1..7, VFX preset, SFX id per emotion. Owner: VMD.
import type { Emotion, EnergyState, VfxPreset } from "../contract/types";
import type { SfxId } from "../audio/synth/sfx";

export interface EmotionMeta {
  label: string;
  /** Short text glyph (MANUAL strip, picker, chips). Emoji-free so it renders the same everywhere. */
  icon: string;
  hotkey: 1 | 2 | 3 | 4 | 5 | 6 | 7;
  vfx: VfxPreset;
  sfx: SfxId;
  /** Additive: tint over the neutral image when the emotion's art is missing (EMO-06). CSS colour. */
  tint: string;
}

export const emotionMeta: Record<Emotion, EmotionMeta> = {
  neutral: { label: "Neutral", icon: "—", hotkey: 1, vfx: "none", sfx: "emo_neutral", tint: "transparent" },
  happy: { label: "Happy", icon: "✦", hotkey: 2, vfx: "sparkle", sfx: "emo_happy", tint: "var(--signal-warn)" },
  sad: { label: "Sad", icon: "☂", hotkey: 3, vfx: "rain", sfx: "emo_sad", tint: "var(--sad-blue)" },
  angry: { label: "Angry", icon: "╬", hotkey: 4, vfx: "anger", sfx: "emo_angry", tint: "var(--signal-err)" },
  surprised: { label: "Surprised", icon: "!", hotkey: 5, vfx: "shock", sfx: "emo_surprised", tint: "var(--paper-50)" },
  thinking: { label: "Thinking", icon: "…", hotkey: 6, vfx: "ponder", sfx: "emo_thinking", tint: "var(--c-glow)" },
  embarrassed: { label: "Embarrassed", icon: "///", hotkey: 7, vfx: "blush", sfx: "emo_embarrassed", tint: "var(--blush)" },
};

/** Emotions in hotkey order (1..7). */
export const EMOTION_ORDER: Emotion[] = ["neutral", "happy", "sad", "angry", "surprised", "thinking", "embarrassed"];

export function emotionForHotkey(key: string): Emotion | null {
  const n = Number(key);
  return EMOTION_ORDER.find((e) => emotionMeta[e].hotkey === n) ?? null;
}

/** Energy-state presentation (doc 04 §6 rows *tired* / *exhausted*). */
export const energyStateMeta: Record<EnergyState, { label: string; vfx: VfxPreset | "yawn" | "none"; sfx: SfxId | null; badge: string | null }> = {
  active: { label: "Active", vfx: "none", sfx: null, badge: null },
  tired: { label: "Tired", vfx: "yawn", sfx: null, badge: "~" },
  exhausted: { label: "Asleep", vfx: "sleep", sfx: "energy_snore", badge: "Zzz" },
};
