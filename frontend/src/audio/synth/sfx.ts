// Procedural SFX recipes (R11, D-52; doc 04 §7.2, VMD paper §2.6). Owner: VMD.
// Every id renders once with OfflineAudioContext into a short AudioBuffer ("SKETCH" quality):
// soft attacks, band-limited (≤ 9 kHz master lowpass), compressed, then peak-normalised per recipe
// so nothing clips and UI ticks sit well below stings. Browser only.
// The EE's audio engine imports `SfxId` and plays `placeholder:sfx/<id>` via resolveAudio().
import { filter, makeRig, osc, outlet, type RenderRig } from "./kit";

export const SFX_IDS = [
  // UI
  "ui_hover", "ui_confirm", "ui_back", "ui_toggle", "ui_send", "ui_first_token", "ui_cutin",
  "ui_pause_open", "ui_pause_close", "ui_stream_tick", "ui_whoosh", "ui_shatter", "ui_flood",
  // Emotions (doc 04 §6)
  "emo_neutral", "emo_happy", "emo_sad", "emo_angry", "emo_surprised", "emo_thinking", "emo_embarrassed",
  // Generation
  "gen_complete", "gen_failed",
  // Ceremonies
  "vs_sting", "round_gong", "verdict_tension", "verdict_sting", "summon_sting",
  // Toasts
  "toast_success", "toast_info", "toast_warn", "toast_error",
  // Energy
  "energy_drain", "energy_topup", "energy_snore",
] as const;

export type SfxId = (typeof SFX_IDS)[number];

export function isSfxId(x: string): x is SfxId {
  return (SFX_IDS as readonly string[]).includes(x);
}

/** Stings and ceremony hits duck the music bus (doc 04 §7.3). The EE engine may read this. */
export const SFX_DUCKS: ReadonlySet<SfxId> = new Set<SfxId>([
  "vs_sting", "round_gong", "verdict_sting", "summon_sting", "verdict_tension",
]);

// ── Building blocks ──────────────────────────────────────────────────────────
interface ToneOpts {
  type?: OscillatorType;
  peak?: number;
  attack?: number;
  /** Glide the pitch to this Hz over `glide` seconds. */
  to?: number;
  glide?: number;
  pan?: number;
  send?: number;
  /** Optional lowpass on this voice (tames square/saw). */
  lp?: number;
  detune?: number;
}

function tone(r: RenderRig, t: number, hz: number, dur: number, o: ToneOpts = {}): void {
  const { ctx } = r;
  const g = ctx.createGain();
  const out = outlet(r, 1, o.pan ?? 0, o.send ?? 0.4);
  const src = osc(ctx, o.type ?? "sine", hz, o.detune ?? 0);
  if (o.to) {
    src.frequency.setValueAtTime(hz, t);
    src.frequency.exponentialRampToValueAtTime(o.to, t + (o.glide ?? dur));
  }
  const a = o.attack ?? 0.004;
  g.gain.setValueAtTime(0, t);
  g.gain.linearRampToValueAtTime(o.peak ?? 0.5, t + a);
  g.gain.exponentialRampToValueAtTime(0.0001, t + a + dur);
  let node: AudioNode = src;
  if (o.lp) node = node.connect(filter(ctx, "lowpass", o.lp, 0.6));
  node.connect(g).connect(out);
  src.start(t);
  src.stop(t + a + dur + 0.05);
}

interface NoiseOpts {
  type?: BiquadFilterType;
  from: number;
  to?: number;
  q?: number;
  peak?: number;
  attack?: number;
  pan?: number;
  send?: number;
  /** Curve the sweep exponentially (default) or linearly. */
  linear?: boolean;
}

function noise(r: RenderRig, t: number, dur: number, o: NoiseOpts): void {
  const { ctx } = r;
  const src = ctx.createBufferSource();
  src.buffer = r.noise;
  src.loop = true;
  const f = filter(ctx, o.type ?? "bandpass", o.from, o.q ?? 1.2);
  if (o.to) {
    f.frequency.setValueAtTime(o.from, t);
    if (o.linear) f.frequency.linearRampToValueAtTime(o.to, t + dur);
    else f.frequency.exponentialRampToValueAtTime(o.to, t + dur);
  }
  const g = ctx.createGain();
  const a = o.attack ?? 0.01;
  g.gain.setValueAtTime(0, t);
  g.gain.linearRampToValueAtTime(o.peak ?? 0.4, t + a);
  g.gain.exponentialRampToValueAtTime(0.0001, t + Math.max(a + 0.01, dur));
  src.connect(f).connect(g).connect(outlet(r, 1, o.pan ?? 0, o.send ?? 0.4));
  src.start(t, (t * 0.37) % 0.5);
  src.stop(t + dur + 0.05);
}

/** Soft additive bell (1 · 2 · 3.01 · 4.2 partials, upper ones decay faster). */
function bell(r: RenderRig, t: number, hz: number, dur: number, peak = 0.35, pan = 0): void {
  const partials: [number, number, number][] = [[1, 1, 1], [2, 0.32, 0.55], [3.01, 0.14, 0.35], [4.2, 0.06, 0.2]];
  for (const [ratio, amp, life] of partials) {
    if (hz * ratio > 9000) continue;
    tone(r, t, hz * ratio, dur * life, { peak: peak * amp, attack: 0.003, pan, send: 0.6 });
  }
}

/** Short brass-ish stab: detuned saws through a closing lowpass. */
function stab(r: RenderRig, t: number, notesHz: number[], dur: number, peak = 0.18, cutoff = 2200): void {
  const { ctx } = r;
  notesHz.forEach((hz, i) => {
    for (const det of [-7, 6]) {
      const src = osc(ctx, "sawtooth", hz, det);
      const f = filter(ctx, "lowpass", cutoff, 0.8);
      f.frequency.setValueAtTime(cutoff, t);
      f.frequency.exponentialRampToValueAtTime(Math.max(300, cutoff * 0.25), t + dur);
      const g = ctx.createGain();
      g.gain.setValueAtTime(0, t);
      g.gain.linearRampToValueAtTime(peak / notesHz.length, t + 0.012);
      g.gain.setTargetAtTime(0, t + dur * 0.4, dur * 0.3);
      src.connect(f).connect(g).connect(outlet(r, 1, (i - (notesHz.length - 1) / 2) * 0.35, 0.7));
      src.start(t);
      src.stop(t + dur * 2);
    }
  });
}

/** Sine-drop impact ("boom"). */
function boom(r: RenderRig, t: number, from = 90, to = 38, dur = 0.5, peak = 0.9): void {
  tone(r, t, from, dur, { to, glide: dur * 0.6, peak, attack: 0.002, send: 0.25 });
  noise(r, t, 0.08, { type: "lowpass", from: 900, peak: 0.25, attack: 0.001, send: 0.1 });
}

const hz = (midi: number) => 440 * Math.pow(2, (midi - 69) / 12);

// ── Recipes ──────────────────────────────────────────────────────────────────
interface Recipe {
  /** Rendered length in seconds (includes tail). */
  len: number;
  /** Peak after normalisation (0..1). UI ticks low, stings higher. */
  peak: number;
  reverb?: { sec: number; mix: number };
  lowpass?: number;
  draw(r: RenderRig): void;
}

const R: Record<SfxId, Recipe> = {
  // ── UI ──
  ui_hover: { len: 0.08, peak: 0.16, draw: (r) => tone(r, 0, 2000, 0.025, { peak: 0.5, attack: 0.002, send: 0 }) },
  ui_confirm: {
    len: 0.32, peak: 0.42,
    draw: (r) => {
      noise(r, 0, 0.14, { from: 300, to: 4000, q: 1.6, peak: 0.5, attack: 0.006 });
      tone(r, 0.05, 1320, 0.09, { peak: 0.35, type: "triangle", send: 0.3 });
    },
  },
  ui_back: {
    len: 0.3, peak: 0.36,
    draw: (r) => {
      noise(r, 0, 0.13, { from: 2600, to: 380, q: 1.4, peak: 0.45 });
      tone(r, 0.02, 660, 0.12, { to: 440, peak: 0.3, type: "triangle", send: 0.2 });
    },
  },
  ui_toggle: {
    len: 0.14, peak: 0.3,
    draw: (r) => {
      tone(r, 0, 1400, 0.03, { peak: 0.4, type: "triangle", send: 0.1 });
      tone(r, 0.045, 1900, 0.04, { peak: 0.4, type: "triangle", send: 0.1 });
    },
  },
  ui_send: {
    len: 0.3, peak: 0.38,
    draw: (r) => {
      noise(r, 0, 0.16, { from: 600, to: 3200, q: 1.1, peak: 0.35 });
      tone(r, 0.01, 700, 0.14, { to: 1400, glide: 0.1, peak: 0.35, type: "triangle", send: 0.3 });
    },
  },
  ui_first_token: { len: 0.12, peak: 0.14, draw: (r) => tone(r, 0, 1600, 0.05, { peak: 0.5, send: 0.4 }) },
  ui_cutin: {
    len: 0.42, peak: 0.42,
    draw: (r) => {
      noise(r, 0, 0.22, { type: "highpass", from: 900, to: 4200, q: 0.8, peak: 0.25, attack: 0.03 });
      boom(r, 0.18, 140, 70, 0.2, 0.5);
    },
  },
  ui_pause_open: {
    len: 0.45, peak: 0.36,
    draw: (r) => {
      [76, 72, 67].forEach((m, i) => tone(r, i * 0.05, hz(m), 0.22, { peak: 0.3, type: "triangle", send: 0.5 }));
      noise(r, 0, 0.18, { from: 3000, to: 500, peak: 0.12 });
    },
  },
  ui_pause_close: {
    len: 0.45, peak: 0.36,
    draw: (r) => {
      [67, 72, 76].forEach((m, i) => tone(r, i * 0.05, hz(m), 0.22, { peak: 0.3, type: "triangle", send: 0.5 }));
      noise(r, 0, 0.18, { from: 500, to: 3000, peak: 0.12 });
    },
  },
  ui_stream_tick: { len: 0.04, peak: 0.08, draw: (r) => tone(r, 0, 3000, 0.008, { peak: 0.5, send: 0 }) },
  ui_whoosh: {
    len: 0.6, peak: 0.34,
    draw: (r) => noise(r, 0, 0.46, { from: 220, to: 2600, q: 1.8, peak: 0.6, attack: 0.18 }),
  },
  ui_shatter: {
    len: 0.8, peak: 0.4, reverb: { sec: 1.2, mix: 0.25 },
    draw: (r) => {
      noise(r, 0, 0.12, { type: "highpass", from: 2500, peak: 0.35, attack: 0.001 });
      const parts = [2093, 2637, 3322, 3951, 4699, 5588];
      parts.forEach((f, i) => tone(r, 0.004 + i * 0.022, f, 0.18 + (i % 3) * 0.08, { peak: 0.12, send: 0.7, pan: ((i % 2) * 2 - 1) * 0.4 }));
      boom(r, 0, 120, 60, 0.18, 0.35);
    },
  },
  ui_flood: {
    len: 0.6, peak: 0.26,
    draw: (r) => noise(r, 0, 0.42, { type: "lowpass", from: 300, to: 2400, q: 2, peak: 0.6, attack: 0.15 }),
  },

  // ── Emotions ──
  emo_neutral: { len: 0.12, peak: 0.12, draw: (r) => tone(r, 0, 880, 0.05, { peak: 0.4, type: "triangle", send: 0.2 }) },
  emo_happy: {
    len: 0.7, peak: 0.34,
    draw: (r) => {
      bell(r, 0, 1568, 0.45, 0.35, -0.15);
      bell(r, 0.06, 2349, 0.5, 0.3, 0.15);
    },
  },
  emo_sad: {
    len: 1.3, peak: 0.36, reverb: { sec: 1.8, mix: 0.25 },
    draw: (r) => {
      // a soft low piano-ish minor dyad (E3 + G3)
      for (const m of [52, 55]) {
        tone(r, 0, hz(m), 1.0, { peak: 0.35, type: "triangle", lp: 1400, attack: 0.008 });
        tone(r, 0, hz(m) * 2, 0.5, { peak: 0.08, attack: 0.005 });
      }
    },
  },
  emo_angry: {
    len: 0.36, peak: 0.5,
    draw: (r) => {
      boom(r, 0, 90, 40, 0.22, 0.9);
      noise(r, 0, 0.06, { type: "bandpass", from: 400, q: 1, peak: 0.3, attack: 0.001, send: 0 });
    },
  },
  emo_surprised: {
    len: 0.22, peak: 0.36,
    draw: (r) => {
      tone(r, 0, 420, 0.06, { to: 980, glide: 0.05, peak: 0.5, send: 0.2 });
      tone(r, 0.05, 1320, 0.05, { peak: 0.2, type: "triangle", send: 0.3 });
    },
  },
  emo_thinking: {
    len: 0.3, peak: 0.24,
    draw: (r) => {
      for (const [t, f] of [[0, 1200], [0.11, 1000]] as const) {
        tone(r, t, f, 0.03, { peak: 0.4, type: "triangle", send: 0.3 });
        noise(r, t, 0.025, { from: 1800, q: 8, peak: 0.25, attack: 0.001, send: 0.2 });
      }
    },
  },
  emo_embarrassed: {
    len: 0.3, peak: 0.28,
    draw: (r) => {
      noise(r, 0, 0.12, { from: 800, to: 3000, q: 2.2, peak: 0.45, attack: 0.02 });
      tone(r, 0.02, 900, 0.1, { to: 1300, peak: 0.18, send: 0.2 });
    },
  },

  // ── Generation ──
  gen_complete: {
    len: 1.1, peak: 0.38,
    draw: (r) => [84, 88, 91, 96].forEach((m, i) => bell(r, i * 0.07, hz(m), 0.6, 0.3, (i - 1.5) * 0.2)),
  },
  gen_failed: {
    len: 0.42, peak: 0.34,
    draw: (r) => {
      tone(r, 0, 146.8, 0.12, { type: "square", lp: 900, peak: 0.35, send: 0.1 });
      tone(r, 0.15, 138.6, 0.16, { type: "square", lp: 800, peak: 0.35, send: 0.1 });
    },
  },

  // ── Ceremonies ──
  vs_sting: {
    len: 1.6, peak: 0.62, reverb: { sec: 1.8, mix: 0.25 },
    draw: (r) => {
      boom(r, 0, 80, 34, 0.9, 1);
      noise(r, 0, 0.5, { type: "lowpass", from: 2400, to: 300, q: 0.7, peak: 0.35, attack: 0.002 });
      stab(r, 0.01, [hz(45), hz(52), hz(57), hz(58)], 0.7, 0.32, 2000);
    },
  },
  round_gong: {
    len: 2.2, peak: 0.5, reverb: { sec: 2.2, mix: 0.3 },
    draw: (r) => {
      // inharmonic partials over 110 Hz, slight downward bend
      const parts: [number, number, number][] = [[1, 1, 1.8], [1.47, 0.5, 1.4], [2.09, 0.42, 1.1], [2.56, 0.3, 0.9], [3.23, 0.2, 0.7], [4.1, 0.12, 0.5]];
      parts.forEach(([k, a, life], i) =>
        tone(r, 0, 110 * k, life, { to: 110 * k * 0.985, glide: life, peak: 0.4 * a, attack: 0.006, pan: (i % 2 ? 1 : -1) * 0.15, send: 0.6 }),
      );
      noise(r, 0, 0.05, { type: "lowpass", from: 1200, peak: 0.25, attack: 0.001 });
    },
  },
  verdict_tension: {
    len: 1.0, peak: 0.34,
    draw: (r) => {
      const { ctx } = r;
      for (const det of [-9, 0, 8]) {
        const src = osc(ctx, "sawtooth", 55, det);
        const f = filter(ctx, "lowpass", 180, 2);
        f.frequency.exponentialRampToValueAtTime(900, 0.8);
        const g = ctx.createGain();
        g.gain.setValueAtTime(0, 0);
        g.gain.linearRampToValueAtTime(0.18, 0.35);
        g.gain.linearRampToValueAtTime(0, 0.92);
        src.connect(f).connect(g).connect(outlet(r, 1, 0, 0.3));
        src.start(0);
        src.stop(1);
      }
    },
  },
  verdict_sting: {
    len: 2.0, peak: 0.62, reverb: { sec: 2, mix: 0.28 },
    draw: (r) => {
      boom(r, 0, 70, 36, 0.8, 0.9);
      stab(r, 0, [hz(48), hz(55), hz(60), hz(64), hz(67)], 0.9, 0.34, 2600);
      [72, 76, 79, 84].forEach((m, i) => bell(r, 0.08 + i * 0.05, hz(m), 0.9, 0.18, (i - 1.5) * 0.25));
    },
  },
  summon_sting: {
    len: 2.0, peak: 0.6, reverb: { sec: 2.2, mix: 0.32 },
    draw: (r) => {
      noise(r, 0, 0.55, { type: "bandpass", from: 400, to: 5200, q: 1.4, peak: 0.45, attack: 0.45 });
      [67, 71, 74, 79, 83, 86].forEach((m, i) => bell(r, 0.1 + i * 0.06, hz(m), 0.8, 0.2, (i - 2.5) * 0.15));
      boom(r, 0.5, 90, 40, 0.7, 0.85);
      stab(r, 0.5, [hz(43), hz(50), hz(55), hz(59), hz(62)], 0.8, 0.28, 2800);
    },
  },

  // ── Toasts ──
  toast_success: { len: 0.6, peak: 0.3, draw: (r) => { bell(r, 0, hz(88), 0.3, 0.3); bell(r, 0.08, hz(95), 0.4, 0.3); } },
  toast_info: { len: 0.5, peak: 0.24, draw: (r) => bell(r, 0, hz(88), 0.35, 0.3) },
  toast_warn: { len: 0.5, peak: 0.28, draw: (r) => { bell(r, 0, hz(81), 0.2, 0.3); bell(r, 0.12, hz(81), 0.3, 0.3); } },
  toast_error: {
    len: 0.5, peak: 0.32,
    draw: (r) => {
      tone(r, 0, hz(64), 0.16, { type: "triangle", peak: 0.35, lp: 2000 });
      tone(r, 0.12, hz(63), 0.26, { type: "triangle", peak: 0.35, lp: 2000 });
    },
  },

  // ── Energy ──
  energy_drain: {
    len: 0.24, peak: 0.24,
    draw: (r) => tone(r, 0, 820, 0.16, { to: 300, glide: 0.14, type: "triangle", peak: 0.4, send: 0.2 }),
  },
  energy_topup: {
    len: 0.85, peak: 0.36,
    draw: (r) => {
      tone(r, 0, 300, 0.55, { to: 1500, glide: 0.5, type: "triangle", peak: 0.3, attack: 0.05, send: 0.3 });
      [0.12, 0.24, 0.36, 0.48, 0.56, 0.62].forEach((t, i) => tone(r, t, 2200 + i * 260, 0.06, { peak: 0.12, send: 0.6, pan: (i % 2 ? 1 : -1) * 0.3 }));
    },
  },
  energy_snore: {
    len: 0.75, peak: 0.22,
    draw: (r) => {
      const { ctx } = r;
      const src = osc(ctx, "sawtooth", 120);
      src.frequency.linearRampToValueAtTime(104, 0.6);
      const lfo = osc(ctx, "sine", 7);
      const lfoG = ctx.createGain();
      lfoG.gain.value = 3;
      lfo.connect(lfoG).connect(src.frequency);
      const f1 = filter(ctx, "bandpass", 500, 3);
      const f2 = filter(ctx, "lowpass", 900, 0.7);
      const g = ctx.createGain();
      g.gain.setValueAtTime(0, 0);
      g.gain.linearRampToValueAtTime(0.5, 0.12);
      g.gain.linearRampToValueAtTime(0.35, 0.45);
      g.gain.linearRampToValueAtTime(0, 0.68);
      src.connect(f1).connect(f2).connect(g).connect(outlet(r, 1, 0, 0.15));
      src.start(0);
      lfo.start(0);
      src.stop(0.72);
      lfo.stop(0.72);
    },
  },
};

/** Peak-normalise to `ceil` with 4 ms fade-in / 12 ms fade-out guards (no clicks). */
function finish(buf: AudioBuffer, ceil: number): AudioBuffer {
  let peak = 0;
  for (let c = 0; c < buf.numberOfChannels; c++) {
    const d = buf.getChannelData(c);
    for (let i = 0; i < d.length; i++) peak = Math.max(peak, Math.abs(d[i]));
  }
  const k = peak > 1e-6 ? ceil / peak : 1;
  const fin = Math.floor(0.004 * buf.sampleRate);
  const fout = Math.floor(0.012 * buf.sampleRate);
  for (let c = 0; c < buf.numberOfChannels; c++) {
    const d = buf.getChannelData(c);
    for (let i = 0; i < d.length; i++) {
      let g = k;
      if (i < fin) g *= i / fin;
      const j = d.length - 1 - i;
      if (j < fout) g *= j / fout;
      d[i] *= g;
    }
  }
  return buf;
}

/** Render one SFX recipe. Deterministic. */
export async function renderSfx(id: SfxId): Promise<AudioBuffer> {
  const rec = R[id];
  if (!rec) throw new Error(`Unknown SFX id: ${id}`);
  const rig = makeRig(rec.len, {
    lowpassHz: rec.lowpass ?? 9000,
    reverbSec: rec.reverb?.sec ?? 0.9,
    reverbMix: rec.reverb?.mix ?? 0.12,
  });
  rec.draw(rig);
  return finish(await rig.ctx.startRendering(), rec.peak);
}
