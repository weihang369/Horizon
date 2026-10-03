// Shared WebAudio building blocks for offline rendering (browser only). Owner: VMD.
export const SAMPLE_RATE = 48000;

export const midiToHz = (m: number) => 440 * Math.pow(2, (m - 69) / 12);

/** A render context with a soft master chain: bus → lowpass → compressor → out, plus a reverb send. */
export interface RenderRig {
  ctx: OfflineAudioContext;
  /** Dry input (goes through the master chain). */
  bus: GainNode;
  /** Reverb send input. */
  verb: GainNode;
  noise: AudioBuffer;
}

export function makeRig(seconds: number, opts?: { lowpassHz?: number; reverbSec?: number; reverbMix?: number }): RenderRig {
  const ctx = new OfflineAudioContext(2, Math.max(1, Math.ceil(seconds * SAMPLE_RATE)), SAMPLE_RATE);
  const bus = ctx.createGain();
  const lp = ctx.createBiquadFilter();
  lp.type = "lowpass";
  lp.frequency.value = opts?.lowpassHz ?? 7000;
  lp.Q.value = 0.5;
  const comp = ctx.createDynamicsCompressor();
  comp.threshold.value = -18;
  comp.ratio.value = 3;
  comp.attack.value = 0.01;
  comp.release.value = 0.2;
  comp.knee.value = 12;
  bus.connect(lp).connect(comp).connect(ctx.destination);

  const verb = ctx.createGain();
  const conv = ctx.createConvolver();
  conv.buffer = impulse(ctx, opts?.reverbSec ?? 1.8);
  const wet = ctx.createGain();
  wet.gain.value = opts?.reverbMix ?? 0.15;
  verb.connect(conv).connect(wet).connect(lp);

  return { ctx, bus, verb, noise: noiseBuffer(ctx, 1) };
}

export function impulse(ctx: BaseAudioContext, seconds: number): AudioBuffer {
  const len = Math.floor(seconds * ctx.sampleRate);
  const buf = ctx.createBuffer(2, len, ctx.sampleRate);
  for (let c = 0; c < 2; c++) {
    const d = buf.getChannelData(c);
    let seed = 1234 + c * 999;
    for (let i = 0; i < len; i++) {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      const r = seed / 4294967296 * 2 - 1;
      d[i] = r * Math.pow(1 - i / len, 3.2);
    }
  }
  return buf;
}

export function noiseBuffer(ctx: BaseAudioContext, seconds: number): AudioBuffer {
  const len = Math.floor(seconds * ctx.sampleRate);
  const buf = ctx.createBuffer(1, len, ctx.sampleRate);
  const d = buf.getChannelData(0);
  let seed = 42;
  for (let i = 0; i < len; i++) {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    d[i] = seed / 4294967296 * 2 - 1;
  }
  return buf;
}

/** Output node with optional stereo pan, feeding the dry bus and the reverb send. */
export function outlet(rig: RenderRig, gain: number, pan = 0, send = 1): GainNode {
  const g = rig.ctx.createGain();
  g.gain.value = gain;
  const p = rig.ctx.createStereoPanner();
  p.pan.value = pan;
  g.connect(p);
  p.connect(rig.bus);
  if (send > 0) {
    const s = rig.ctx.createGain();
    s.gain.value = send;
    p.connect(s).connect(rig.verb);
  }
  return g;
}

/** ADSR-ish envelope on a gain param. All times in seconds. */
export function adsr(p: AudioParam, t: number, peak: number, a: number, d: number, sustain: number, end: number, r: number): void {
  p.setValueAtTime(0, t);
  p.linearRampToValueAtTime(peak, t + a);
  p.setTargetAtTime(peak * sustain, t + a, Math.max(0.005, d / 3));
  const rel = Math.max(end, t + a + 0.01);
  p.setTargetAtTime(0, rel, Math.max(0.005, r / 4));
}

/** Percussive decay envelope. */
export function perc(p: AudioParam, t: number, peak: number, decay: number, attack = 0.004): void {
  p.setValueAtTime(0, t);
  p.linearRampToValueAtTime(peak, t + attack);
  p.exponentialRampToValueAtTime(0.0001, t + attack + decay);
}

export function osc(ctx: BaseAudioContext, type: OscillatorType, hz: number, detuneCents = 0): OscillatorNode {
  const o = ctx.createOscillator();
  o.type = type;
  o.frequency.value = hz;
  o.detune.value = detuneCents;
  return o;
}

export function filter(ctx: BaseAudioContext, type: BiquadFilterType, hz: number, q = 0.7): BiquadFilterNode {
  const f = ctx.createBiquadFilter();
  f.type = type;
  f.frequency.value = hz;
  f.Q.value = q;
  return f;
}

/** Normalise a rendered buffer to a target RMS with a peak ceiling (consistent loudness across tracks). */
export function normalise(buf: AudioBuffer, targetRms = 0.085, peakCeil = 0.72, gainDb = 0): AudioBuffer {
  let sum = 0;
  let peak = 0;
  let n = 0;
  for (let c = 0; c < buf.numberOfChannels; c++) {
    const d = buf.getChannelData(c);
    for (let i = 0; i < d.length; i++) {
      const v = d[i];
      sum += v * v;
      const a = Math.abs(v);
      if (a > peak) peak = a;
    }
    n += d.length;
  }
  const rms = Math.sqrt(sum / Math.max(1, n));
  if (rms < 1e-6) return buf;
  let k = (targetRms / rms) * Math.pow(10, gainDb / 20);
  if (peak * k > peakCeil) k = peakCeil / peak;
  for (let c = 0; c < buf.numberOfChannels; c++) {
    const d = buf.getChannelData(c);
    for (let i = 0; i < d.length; i++) d[i] *= k;
  }
  return buf;
}

/** Fold the reverb tail (everything after loopLen) back onto the start, for a seamless loop. */
export function foldLoop(src: AudioBuffer, loopSec: number): AudioBuffer {
  const len = Math.min(src.length, Math.round(loopSec * src.sampleRate));
  const out = new AudioBuffer({ length: len, numberOfChannels: src.numberOfChannels, sampleRate: src.sampleRate });
  for (let c = 0; c < src.numberOfChannels; c++) {
    const s = src.getChannelData(c);
    const d = out.getChannelData(c);
    d.set(s.subarray(0, len));
    for (let i = len; i < s.length; i++) {
      const j = i - len;
      if (j >= len) break;
      d[j] += s[i];
    }
    // 5 ms edge ramps guard against clicks at the seam
    const ramp = Math.floor(0.005 * src.sampleRate);
    for (let i = 0; i < ramp; i++) {
      const k = i / ramp;
      d[len - 1 - i] *= 0.5 + 0.5 * k;
    }
  }
  return out;
}

/** Karplus–Strong pluck rendered in JS (no DelayNode feedback limits). */
export function ksPluck(ctx: BaseAudioContext, hz: number, seconds: number, brightness = 0.5, seed = 1): AudioBuffer {
  const sr = ctx.sampleRate;
  const len = Math.floor(seconds * sr);
  const buf = ctx.createBuffer(1, len, sr);
  const d = buf.getChannelData(0);
  const N = Math.max(2, Math.round(sr / hz));
  const ring = new Float32Array(N);
  let s = seed >>> 0;
  let prev = 0;
  for (let i = 0; i < N; i++) {
    s = (s * 1664525 + 1013904223) >>> 0;
    const r = s / 4294967296 * 2 - 1;
    prev = prev + brightness * (r - prev); // pre-filter the excitation
    ring[i] = prev;
  }
  let idx = 0;
  const decay = 0.996;
  for (let i = 0; i < len; i++) {
    const a = ring[idx];
    const b = ring[(idx + 1) % N];
    const v = 0.5 * (a + b) * decay;
    d[i] = a;
    ring[idx] = v;
    idx = (idx + 1) % N;
  }
  return buf;
}
