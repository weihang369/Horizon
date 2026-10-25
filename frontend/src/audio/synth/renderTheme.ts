// renderTheme(spec) → AudioBuffer: a tasteful 8-bar procedural loop from a song brief (R11, D-52).
// BPM → tempo · mood → mode · genre → groove · instruments → voices · seeded PRNG per character.
// Everything is filtered (master lowpass 7 kHz), compressed and RMS-normalised, so themes sit at the
// same soft level. Browser only (OfflineAudioContext).
import { makeRng, type Rng } from "./prng";
import { planFromSpec, type Groove, type ModeName, type ThemeProcSpec, type Voice } from "./spec";
import {
  SAMPLE_RATE, adsr, filter, foldLoop, ksPluck, makeRig, midiToHz, normalise, osc, outlet, perc, type RenderRig,
} from "./kit";

const MODE_STEPS: Record<ModeName, number[]> = {
  ionian: [0, 2, 4, 5, 7, 9, 11],
  dorian: [0, 2, 3, 5, 7, 9, 10],
  phrygian: [0, 1, 3, 5, 7, 8, 10],
  lydian: [0, 2, 4, 6, 7, 9, 11],
  mixolydian: [0, 2, 4, 5, 7, 9, 10],
  aeolian: [0, 2, 3, 5, 7, 8, 10],
  major_pent: [0, 2, 4, 5, 7, 9, 11],
  minor_pent: [0, 2, 3, 5, 7, 8, 10],
};
const PENTA: Partial<Record<ModeName, number[]>> = { major_pent: [0, 2, 4, 7, 9], minor_pent: [0, 3, 5, 7, 10] };

const PROGRESSIONS: Record<ModeName, number[][]> = {
  ionian: [[0, 4, 5, 3], [0, 5, 3, 4], [3, 4, 2, 5], [0, 3, 5, 4]],
  major_pent: [[0, 5, 3, 4], [0, 3, 0, 4], [0, 4, 5, 3]],
  lydian: [[0, 1, 0, 1], [0, 1, 4, 0], [0, 1, 5, 4]],
  mixolydian: [[0, 6, 3, 0], [0, 3, 6, 0], [0, 6, 3, 4]],
  dorian: [[0, 3, 0, 3], [0, 6, 3, 0], [0, 2, 3, 0], [0, 3, 6, 4]],
  aeolian: [[0, 5, 2, 6], [0, 3, 6, 2], [0, 5, 3, 4]],
  minor_pent: [[0, 5, 2, 6], [0, 3, 6, 4], [0, 6, 5, 6]],
  phrygian: [[0, 1, 0, 6], [0, 1, 5, 1], [0, 6, 1, 0]],
};

const SEVENTHS: Groove[] = ["lofi", "jazzhop", "citypop", "bossa"];
const SWING: Partial<Record<Groove, number>> = { lofi: 0.62, jazzhop: 0.64, folk: 0.6, bossa: 0.5 };

interface Ctx {
  rig: RenderRig;
  rng: Rng;
  scale: number[];
  key: number; // MIDI of the tonic, octave 3
  beat: number; // seconds per beat
  groove: Groove;
  mode: ModeName;
  voices: Set<Voice>;
  plucks: Map<string, AudioBuffer>;
}

const deg = (c: Ctx, d: number, base: number) => base + c.scale[((d % 7) + 7) % 7] + 12 * Math.floor(d / 7);

function chordTones(c: Ctx, root: number): number[] {
  const t = [root, root + 2, root + 4];
  if (SEVENTHS.includes(c.groove)) t.push(root + 6);
  if (c.groove === "jazzhop") t.push(root + 8);
  return t.map((d) => {
    let m = deg(c, d, c.key);
    while (m > c.key + 16) m -= 12;
    return m;
  });
}

// ── Voices ────────────────────────────────────────────────────────────────────
function keys(c: Ctx, t: number, m: number, dur: number, vel: number, pan = 0) {
  const { ctx } = c.rig;
  const out = outlet(c.rig, 1, pan, 0.9);
  const g = ctx.createGain();
  const lp = filter(ctx, "lowpass", c.groove === "lofi" || c.groove === "jazzhop" ? 1900 : 3200);
  const a = osc(ctx, "sine", midiToHz(m), (c.rng.next() - 0.5) * 8);
  const b = osc(ctx, "triangle", midiToHz(m) * 2);
  const bg = ctx.createGain();
  bg.gain.value = 0.18;
  a.connect(g);
  b.connect(bg).connect(g);
  g.connect(lp).connect(out);
  adsr(g.gain, t, 0.2 * vel, 0.008, 0.9, 0.35, t + dur, 0.35);
  a.start(t);
  b.start(t);
  a.stop(t + dur + 0.6);
  b.stop(t + dur + 0.6);
}

function pad(c: Ctx, t: number, m: number, dur: number, vel: number, pan = 0) {
  const { ctx } = c.rig;
  const out = outlet(c.rig, 1, pan, 1.4);
  const g = ctx.createGain();
  const lp = filter(ctx, "lowpass", 1000, 0.4);
  [-7, 7].forEach((det) => {
    const o = osc(ctx, "sawtooth", midiToHz(m), det);
    o.connect(g);
    o.start(t);
    o.stop(t + dur + 1.2);
  });
  g.connect(lp).connect(out);
  adsr(g.gain, t, 0.035 * vel, 0.5, 0.5, 0.85, t + dur, 0.9);
}

function bells(c: Ctx, t: number, m: number, dur: number, vel: number, pan = 0) {
  const { ctx } = c.rig;
  const out = outlet(c.rig, 1, pan, 1.2);
  const f = midiToHz(m);
  const car = osc(ctx, "sine", f);
  const mod = osc(ctx, "sine", f * 3.5);
  const mg = ctx.createGain();
  mg.gain.setValueAtTime(f * 1.6, t);
  mg.gain.exponentialRampToValueAtTime(1, t + 0.9);
  mod.connect(mg).connect(car.frequency);
  const g = ctx.createGain();
  car.connect(g).connect(out);
  perc(g.gain, t, 0.1 * vel, Math.max(0.6, Math.min(1.8, dur + 0.8)));
  car.start(t);
  mod.start(t);
  car.stop(t + 2.2);
  mod.stop(t + 2.2);
}

function pluckVoice(c: Ctx, t: number, m: number, dur: number, vel: number, pan = 0, bright = 0.5) {
  const { ctx } = c.rig;
  const k = `${m}:${bright}`;
  let buf = c.plucks.get(k);
  if (!buf) {
    buf = ksPluck(ctx, midiToHz(m), 2, bright, m * 31 + 7);
    c.plucks.set(k, buf);
  }
  const src = ctx.createBufferSource();
  src.buffer = buf;
  const g = ctx.createGain();
  const out = outlet(c.rig, 1, pan, 0.6);
  src.connect(g).connect(out);
  g.gain.setValueAtTime(0.32 * vel, t);
  g.gain.setTargetAtTime(0, t + Math.max(0.12, dur), 0.08);
  src.start(t);
  src.stop(t + Math.max(0.12, dur) + 0.5);
}

function chip(c: Ctx, t: number, m: number, dur: number, vel: number, pan = 0) {
  const { ctx } = c.rig;
  const out = outlet(c.rig, 1, pan, 0.3);
  const o = osc(ctx, "square", midiToHz(m));
  const lp = filter(ctx, "lowpass", 3800);
  const g = ctx.createGain();
  o.connect(lp).connect(g).connect(out);
  adsr(g.gain, t, 0.045 * vel, 0.004, 0.12, 0.6, t + dur * 0.9, 0.05);
  o.start(t);
  o.stop(t + dur + 0.2);
}

function arp(c: Ctx, t: number, m: number, dur: number, vel: number, pan = 0) {
  const { ctx } = c.rig;
  const out = outlet(c.rig, 1, pan, 0.8);
  const o = osc(ctx, c.groove === "chiptune" ? "square" : "sawtooth", midiToHz(m));
  const lp = filter(ctx, "lowpass", 1600, 3);
  lp.frequency.setValueAtTime(2600, t);
  lp.frequency.exponentialRampToValueAtTime(700, t + 0.18);
  const g = ctx.createGain();
  o.connect(lp).connect(g).connect(out);
  perc(g.gain, t, 0.05 * vel, Math.min(0.3, dur + 0.05));
  o.start(t);
  o.stop(t + 0.4);
}

function bass(c: Ctx, t: number, m: number, dur: number, vel: number) {
  const { ctx } = c.rig;
  const out = outlet(c.rig, 1, 0, 0);
  const a = osc(ctx, "sine", midiToHz(m));
  const b = osc(ctx, c.groove === "citypop" ? "sawtooth" : "triangle", midiToHz(m));
  const lp = filter(ctx, "lowpass", c.groove === "citypop" ? 900 : 520, 1);
  if (c.groove === "citypop") {
    lp.frequency.setValueAtTime(1800, t);
    lp.frequency.exponentialRampToValueAtTime(500, t + 0.15);
  }
  const bg = ctx.createGain();
  bg.gain.value = 0.45;
  const g = ctx.createGain();
  a.connect(g);
  b.connect(bg).connect(g);
  g.connect(lp).connect(out);
  adsr(g.gain, t, 0.3 * vel, 0.006, 0.3, 0.6, t + dur * 0.92, 0.06);
  a.start(t);
  b.start(t);
  a.stop(t + dur + 0.3);
  b.stop(t + dur + 0.3);
}

function strings(c: Ctx, t: number, m: number, vel: number, pan = 0) {
  const { ctx } = c.rig;
  const out = outlet(c.rig, 1, pan, 1);
  const o = osc(ctx, "triangle", midiToHz(m));
  const g = ctx.createGain();
  o.connect(g).connect(out);
  perc(g.gain, t, 0.13 * vel, 0.28);
  o.start(t);
  o.stop(t + 0.4);
}

function brass(c: Ctx, t: number, m: number, dur: number, vel: number, pan = 0) {
  const { ctx } = c.rig;
  const out = outlet(c.rig, 1, pan, 1.1);
  const lp = filter(ctx, "lowpass", 400, 1.2);
  lp.frequency.setValueAtTime(350, t);
  lp.frequency.linearRampToValueAtTime(1200, t + 0.12);
  lp.frequency.setTargetAtTime(850, t + 0.12, 0.2);
  const g = ctx.createGain();
  [0, 5].forEach((det) => {
    const o = osc(ctx, "sawtooth", midiToHz(m), det);
    o.connect(lp);
    o.start(t);
    o.stop(t + dur + 0.6);
  });
  lp.connect(g).connect(out);
  adsr(g.gain, t, 0.045 * vel, 0.08, 0.4, 0.75, t + dur, 0.3);
}

function harmonica(c: Ctx, t: number, m: number, dur: number, vel: number, pan = 0) {
  const { ctx } = c.rig;
  const out = outlet(c.rig, 1, pan, 0.9);
  const bp = filter(ctx, "bandpass", 1300, 1.2);
  const g = ctx.createGain();
  const lfo = osc(ctx, "sine", 5.5);
  const lg = ctx.createGain();
  lg.gain.value = 7;
  lfo.connect(lg);
  [0, 6].forEach((det) => {
    const o = osc(ctx, "square", midiToHz(m), det);
    lg.connect(o.detune);
    o.connect(bp);
    o.start(t);
    o.stop(t + dur + 0.3);
  });
  bp.connect(g).connect(out);
  adsr(g.gain, t, 0.06 * vel, 0.05, 0.2, 0.8, t + dur, 0.12);
  lfo.start(t);
  lfo.stop(t + dur + 0.3);
}

function kick(c: Ctx, t: number, vel: number) {
  const { ctx } = c.rig;
  const out = outlet(c.rig, 1, 0, 0);
  const o = osc(ctx, "sine", 130);
  o.frequency.setValueAtTime(c.groove === "orchestral" ? 90 : 130, t);
  o.frequency.exponentialRampToValueAtTime(45, t + 0.12);
  const g = ctx.createGain();
  o.connect(g).connect(out);
  perc(g.gain, t, 0.75 * vel, c.groove === "orchestral" ? 0.7 : 0.32, 0.002);
  o.start(t);
  o.stop(t + 0.8);
}

function noiseHit(c: Ctx, t: number, type: BiquadFilterType, hz: number, q: number, peak: number, decay: number, pan = 0) {
  const { ctx } = c.rig;
  const src = ctx.createBufferSource();
  src.buffer = c.rig.noise;
  const f = filter(ctx, type, hz, q);
  const g = ctx.createGain();
  const out = outlet(c.rig, 1, pan, type === "bandpass" ? 0.5 : 0.1);
  src.connect(f).connect(g).connect(out);
  perc(g.gain, t, peak, decay, 0.001);
  src.start(t, (t * 7.3) % 0.8);
  src.stop(t + decay + 0.05);
}

const hat = (c: Ctx, t: number, vel: number) => noiseHit(c, t, "highpass", 7500, 0.7, 0.055 * vel, 0.035, 0.25);
function snare(c: Ctx, t: number, vel: number) {
  noiseHit(c, t, "bandpass", 1900, 0.8, (c.groove === "lofi" || c.groove === "jazzhop" ? 0.14 : 0.2) * vel, 0.13, -0.05);
  const { ctx } = c.rig;
  const o = osc(ctx, "triangle", 190);
  const g = ctx.createGain();
  o.connect(g).connect(outlet(c.rig, 1, 0, 0.2));
  perc(g.gain, t, 0.12 * vel, 0.07);
  o.start(t);
  o.stop(t + 0.15);
}
const rim = (c: Ctx, t: number, vel: number) => noiseHit(c, t, "bandpass", 3200, 4, 0.12 * vel, 0.03, 0.2);

function crackle(c: Ctx, seconds: number) {
  const { ctx } = c.rig;
  const len = Math.floor(seconds * ctx.sampleRate);
  const buf = ctx.createBuffer(1, len, ctx.sampleRate);
  const d = buf.getChannelData(0);
  let lp = 0;
  for (let i = 0; i < len; i++) {
    const r = c.rng.next() * 2 - 1;
    lp += 0.08 * (r - lp);
    d[i] = lp * 0.02;
  }
  const clicks = Math.floor(seconds * 9);
  for (let k = 0; k < clicks; k++) {
    const at = Math.floor(c.rng.next() * (len - 64));
    const amp = (0.05 + c.rng.next() * 0.14) * (c.rng.chance(0.5) ? 1 : -1);
    for (let j = 0; j < 40; j++) d[at + j] += amp * Math.exp(-j / 6);
  }
  const src = ctx.createBufferSource();
  src.buffer = buf;
  const f = filter(ctx, "bandpass", 2500, 0.5);
  src.connect(f).connect(outlet(c.rig, 0.7, 0, 0));
  src.start(0);
}

// ── Arrangement ───────────────────────────────────────────────────────────────
function melodyVoice(c: Ctx): ((t: number, m: number, d: number, v: number) => void) | null {
  if (c.voices.has("harmonica")) return (t, m, d, v) => harmonica(c, t, m, d, v, 0.15);
  if (c.voices.has("bells")) return (t, m, d, v) => bells(c, t, m, d, v, 0.2);
  switch (c.groove) {
    case "chiptune": return (t, m, d, v) => chip(c, t, m, d, v, 0.1);
    case "piano": case "lofi": case "jazzhop": return (t, m, d, v) => keys(c, t, m, d, v * 0.8, 0.15);
    case "folk": case "bossa": case "rock": return (t, m, d, v) => pluckVoice(c, t, m, d, v * 0.9, 0.2, 0.7);
    case "orchestral": return (t, m, d, v) => bells(c, t, m, d, v * 0.8, 0.1);
    default: return null;
  }
}

function render(c: Ctx, bars: number) {
  const { rng, groove, beat, voices } = c;
  const step = beat / 4; // 16th
  const swing = SWING[groove] ?? 0.5;
  const tAt = (bar: number, s: number) => {
    const eighthOff = s % 4 === 2 ? (2 * swing - 1) * (beat / 2) : 0;
    return Math.max(0.001, bar * 4 * beat + s * step + eighthOff + (rng.next() - 0.5) * 0.006);
  };
  const prog = rng.pick(PROGRESSIONS[c.mode]);
  const melodyPool = PENTA[c.mode];
  const playMelody = melodyVoice(c);
  // A 4-bar phrase, repeated with a varied ending → sounds composed, not random.
  const phrase = buildPhrase(c, prog, melodyPool);

  for (let bar = 0; bar < bars; bar++) {
    const chordDeg = prog[Math.floor(bar / 2) % prog.length];
    const tones = chordTones(c, chordDeg);
    const root = deg(c, chordDeg, c.key - 12);
    const bassRoot = root < 36 ? root + 12 : root;
    const firstOfChord = bar % 2 === 0;

    // Harmony
    if (voices.has("pad") && firstOfChord) tones.slice(0, 4).forEach((m, i) => pad(c, tAt(bar, 0), m, beat * 8 - 0.1, 1, (i - 1.5) * 0.3));
    if (voices.has("keys")) {
      if (groove === "piano") {
        for (let s = 0; s < 16; s += 2) {
          const idx = [0, 1, 2, 1, 3, 2, 1, 2][s / 2] % tones.length;
          keys(c, tAt(bar, s), tones[idx] + (s >= 8 && idx === 0 ? 12 : 0), beat * 0.9, 0.8, -0.2 + idx * 0.15);
        }
      } else {
        const hits = groove === "citypop" ? [[0, 3], [6, 2], [10, 4], [14, 2]] : [[0, 6], [6, 10]];
        hits.forEach(([s, len]) => tones.forEach((m, i) => keys(c, tAt(bar, s) + i * 0.012, m, len * step, 0.75, (i - 1.5) * 0.25)));
      }
    }
    if (voices.has("guitar")) {
      const pattern = groove === "bossa" ? [0, 3, 6, 10, 12] : groove === "rock" ? [0, 2, 4, 6, 8, 10, 12, 14] : [0, 4, 6, 8, 12, 14];
      pattern.forEach((s, k) => {
        const notes = groove === "rock" ? [tones[0], tones[0] + 7, tones[0] + 12] : groove === "bossa" ? tones.slice(1, 3) : tones;
        const up = groove === "folk" && k % 2 === 1;
        (up ? [...notes].reverse() : notes).forEach((m, i) =>
          pluckVoice(c, tAt(bar, s) + i * 0.014, m, groove === "rock" ? step * 1.4 : step * 3.5, groove === "rock" ? 0.45 : 0.6, -0.3 + i * 0.2, 0.55),
        );
      });
    }
    if (voices.has("strings")) {
      for (let s = 0; s < 16; s += 2) strings(c, tAt(bar, s), tones[(s / 2) % tones.length] + 12, s % 4 === 0 ? 0.9 : 0.6, (s / 16) - 0.4);
    }
    if (voices.has("brass") && firstOfChord) tones.slice(0, 3).forEach((m, i) => brass(c, tAt(bar, 0), m, beat * 3, 0.9, (i - 1) * 0.3));
    if (voices.has("arp")) {
      const rate = groove === "chiptune" ? 1 : 2;
      const shape = [0, 1, 2, 3, 2, 1];
      for (let s = 0, k = 0; s < 16; s += rate, k++) {
        const i = shape[k % shape.length] % tones.length;
        arp(c, tAt(bar, s), tones[i] + 12, step * rate, s % 4 === 0 ? 1 : 0.7, Math.sin(k) * 0.3);
      }
    }

    // Bass
    if (voices.has("bass")) {
      const fifth = bassRoot + 7;
      const pat: [number, number, number][] =
        groove === "citypop" ? [0, 2, 4, 6, 8, 10, 12, 14].map((s, i) => [s, i % 2 ? bassRoot + 12 : bassRoot, 2])
        : groove === "chiptune" || groove === "rock" ? [0, 2, 4, 6, 8, 10, 12, 14].map((s) => [s, bassRoot, 2])
        : groove === "edm" ? [2, 6, 10, 14].map((s) => [s, bassRoot, 2])
        : groove === "synthwave" ? [0, 2, 4, 6, 8, 10, 12, 14].map((s, i) => [s, i % 2 ? bassRoot + 12 : bassRoot, 2])
        : groove === "jazzhop" ? [[0, bassRoot, 4], [4, deg(c, chordDeg + 2, c.key - 12), 4], [8, fifth, 4], [12, bassRoot + 11, 4]]
        : groove === "bossa" ? [[0, bassRoot, 6], [6, fifth, 2], [8, fifth, 6], [14, bassRoot, 2]]
        : groove === "orchestral" ? [[0, bassRoot, 8], [8, fifth - 12, 8]]
        : [[0, bassRoot, 6], [10, fifth, 4]];
      pat.forEach(([s, m, len]) => bass(c, tAt(bar, s), m, len * step, s % 8 === 0 ? 1 : 0.8));
    }

    // Drums
    if (voices.has("drums")) {
      const d = DRUMS[groove];
      d.kick.forEach((s) => kick(c, tAt(bar, s), s === 0 ? 1 : 0.8));
      d.snare.forEach((s) => snare(c, tAt(bar, s), 0.9));
      d.hat.forEach((s, i) => hat(c, tAt(bar, s), i % 2 ? 0.55 : 0.9));
      d.rim?.forEach((s) => rim(c, tAt(bar, s), 0.8));
    } else if (groove === "orchestral" && bar % 2 === 0) {
      kick(c, tAt(bar, 0), 0.5);
    }

    // Melody
    if (playMelody) {
      const notes = phrase[bar % 4];
      const varied = bar >= 4 && bar % 4 >= 2;
      notes.forEach(([s, m, len]) => playMelody(tAt(bar, s), m, len * step, s % 8 === 0 ? 0.9 : 0.7));
      if (varied && bar === bars - 1) playMelody(tAt(bar, 12), deg(c, 0, c.key + 12), 4 * step, 0.8);
    }
  }
}

const DRUMS: Record<Groove, { kick: number[]; snare: number[]; hat: number[]; rim?: number[] }> = {
  lofi: { kick: [0, 7, 10], snare: [4, 12], hat: [0, 2, 4, 6, 8, 10, 12, 14] },
  jazzhop: { kick: [0, 7, 10], snare: [4, 12], hat: [0, 2, 4, 6, 8, 10, 12, 14] },
  citypop: { kick: [0, 8, 11], snare: [4, 12], hat: [0, 2, 4, 6, 8, 10, 12, 14] },
  chiptune: { kick: [0, 8, 10], snare: [4, 12], hat: [0, 2, 4, 6, 8, 10, 12, 14] },
  orchestral: { kick: [0], snare: [], hat: [] },
  folk: { kick: [0, 8], snare: [4, 12], hat: [2, 6, 10, 14] },
  synthwave: { kick: [0, 4, 8, 12], snare: [4, 12], hat: [2, 6, 10, 14] },
  piano: { kick: [], snare: [], hat: [] },
  bossa: { kick: [0, 6, 8, 14], snare: [], hat: [0, 4, 8, 12], rim: [3, 6, 10, 13] },
  ambient: { kick: [], snare: [], hat: [] },
  rock: { kick: [0, 8, 10], snare: [4, 12], hat: [0, 2, 4, 6, 8, 10, 12, 14] },
  edm: { kick: [0, 4, 8, 12], snare: [4, 12], hat: [2, 6, 10, 14] },
};

function buildPhrase(c: Ctx, prog: number[], pool: number[] | undefined): [number, number, number][][] {
  const density = c.groove === "ambient" ? 0.25 : c.groove === "chiptune" ? 0.65 : c.groove === "piano" ? 0.4 : 0.5;
  const top = c.key + 12;
  const pitch = (d: number) =>
    pool ? top + pool[((d % 5) + 5) % 5] + 12 * Math.floor(d / 5) : deg(c, d, top);
  const bars: [number, number, number][][] = [];
  let cur = 2;
  for (let bar = 0; bar < 4; bar++) {
    const chordDeg = prog[Math.floor(bar / 2) % prog.length];
    const notes: [number, number, number][] = [];
    for (let e = 0; e < 8; e++) {
      const strong = e % 4 === 0;
      if (!c.rng.chance(strong ? Math.min(0.95, density + 0.3) : density)) continue;
      const move = c.rng.pick([-2, -1, -1, 0, 1, 1, 2]);
      cur = Math.max(-1, Math.min(pool ? 9 : 11, cur + move));
      // pull strong beats to chord tones
      let d = cur;
      if (strong && !pool) {
        const tones = [chordDeg, chordDeg + 2, chordDeg + 4];
        d = tones.reduce((best, t) => (Math.abs(t - cur) < Math.abs(best - cur) ? t : best), tones[0]);
      }
      notes.push([e * 2, pitch(d), 2]);
    }
    // cadence: bar 4 ends on the tonic
    if (bar === 3) {
      while (notes.length && notes[notes.length - 1][0] >= 10) notes.pop();
      notes.push([10, pitch(0), 6]);
    }
    // extend notes to the next onset (legato), capped at 4 sixteenths
    for (let i = 0; i < notes.length - 1; i++) notes[i][2] = Math.min(4, notes[i + 1][0] - notes[i][0]);
    bars.push(notes);
  }
  return bars;
}

/** Render a theme loop. Deterministic for a given spec. */
export async function renderTheme(spec: ThemeProcSpec): Promise<AudioBuffer> {
  const plan = planFromSpec(spec);
  const rng = makeRng(spec.seed);
  const beat = 60 / plan.bpm;
  const loopSec = plan.bars * 4 * beat;
  const tail = 2.2;
  const rig = makeRig(loopSec + tail, {
    lowpassHz: plan.groove === "lofi" || plan.groove === "jazzhop" ? 5200 : 7000,
    reverbSec: plan.groove === "ambient" ? 3 : 1.8,
    reverbMix: plan.groove === "ambient" ? 0.3 : 0.15,
  });
  const c: Ctx = {
    rig, rng,
    scale: MODE_STEPS[plan.mode],
    key: 48 + rng.int(0, 7), // C3..G3
    beat,
    groove: plan.groove,
    mode: plan.mode,
    voices: new Set(plan.voices),
    plucks: new Map(),
  };
  if (c.voices.has("crackle")) crackle(c, loopSec + tail);
  render(c, plan.bars);
  const rendered = await rig.ctx.startRendering();
  return normalise(foldLoop(rendered, loopSec), 0.085, 0.72, spec.gainDb ?? 0);
}

export { SAMPLE_RATE };
