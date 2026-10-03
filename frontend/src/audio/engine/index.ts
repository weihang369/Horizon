// Audio engine (README §3.6, EE paper §2.8, MUS-01..10). Owner: EE. Buffer-only and outside React (D5).
// Graph: deckA/deckB → music bus → duck → master → compressor → out;  sfx bus → master.
// Buffers come from the VMD's resolveAudio(url), so swapping placeholders for real files is a URL change only (R11).
// resolve.ts + the synth recipes load lazily on unlock (they're ~8 KB gz and never needed before a gesture).
import type { SfxId } from "../synth/sfx";
import { onPrefsAudio } from "../../stores/prefs";
import type { Prefs } from "../../stores/prefs";

export interface MusicOpts { crossfadeMs?: number; label?: string; gainDb?: number }
export interface AudioState {
  unlocked: boolean;
  /** Autoplay was refused: the mini-player shows "▶ Enable audio" (MUS-06). */
  blocked: boolean;
  track: { url: string; label: string; procedural: boolean } | null;
  loading: boolean;
}

const RAMP = 0.005;
const DUCK_LEVEL = 0.4;
const DUCK_ATTACK = 0.06;
const DUCK_HOLD = 0.5;
const DUCK_RELEASE = 0.6;
const MAX_CROSSFADE = 2000;

type ResolveMod = typeof import("../resolve");
type SfxMod = typeof import("../synth/sfx");
let resolveMod: Promise<ResolveMod> | null = null;
let sfxMod: Promise<SfxMod> | null = null;
const loadResolve = () => (resolveMod ??= import("../resolve"));
const loadSfx = () => (sfxMod ??= import("../synth/sfx"));
let ducks: ReadonlySet<string> = new Set();
const resolveAudio = (url: string) => loadResolve().then((m) => m.resolveAudio(url));
/** Same rule as the VMD's isProceduralAudio (kept sync for the mini-player label). */
const isProceduralAudio = (url: string) => url.startsWith("placeholder:") || /\.proc\.json(\?|#|$)/.test(url);

interface Deck { src: AudioBufferSourceNode; gain: GainNode; url: string }

class AudioEngine {
  private ctx: AudioContext | null = null;
  private master!: GainNode;
  private music!: GainNode;
  private duckNode!: GainNode;
  private sfx!: GainNode;
  private deck: Deck | null = null;
  private want: { url: string | null; opts: MusicOpts } = { url: null, opts: {} };
  private musicToken = 0;
  private sfxBuffers = new Map<string, AudioBuffer>();
  private prefs: Prefs["audio"] | null = null;
  private state: AudioState = { unlocked: false, blocked: false, track: null, loading: false };
  private listeners = new Set<(s: AudioState) => void>();
  private unlocking: Promise<void> | null = null;

  constructor() {
    onPrefsAudio((p) => {
      this.prefs = p.audio;
      this.applyVolumes();
    });
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", () => {
        if (!this.ctx) return;
        if (document.hidden) void this.ctx.suspend();
        else if (this.state.unlocked) void this.ctx.resume();
      });
    }
  }

  getState(): AudioState { return this.state; }
  subscribe(cb: (s: AudioState) => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }
  private set(patch: Partial<AudioState>): void {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((cb) => cb(this.state));
  }

  /** First user gesture (APP-01, MUS-06). Safe to call repeatedly. */
  unlock(): Promise<void> {
    if (this.state.unlocked) return Promise.resolve();
    if (this.unlocking) return this.unlocking;
    this.unlocking = (async () => {
      try {
        if (!this.ctx) this.build();
        await this.ctx!.resume();
        if (this.ctx!.state !== "running") throw new Error("audio blocked");
        this.set({ unlocked: true, blocked: false });
        void this.prerenderSfx();
        if (this.want.url) this.setMusic(this.want.url, { ...this.want.opts, crossfadeMs: 1500 });
      } catch {
        this.set({ blocked: true });
      } finally {
        this.unlocking = null;
      }
    })();
    return this.unlocking;
  }

  private build(): void {
    const ctx = new AudioContext({ latencyHint: "interactive" });
    this.ctx = ctx;
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -10;
    comp.ratio.value = 3;
    this.master = ctx.createGain();
    this.music = ctx.createGain();
    this.duckNode = ctx.createGain();
    this.sfx = ctx.createGain();
    this.music.connect(this.duckNode).connect(this.master);
    this.sfx.connect(this.master);
    this.master.connect(comp).connect(ctx.destination);
    this.applyVolumes();
  }

  private async prerenderSfx(): Promise<void> {
    const { SFX_IDS, SFX_DUCKS } = await loadSfx();
    ducks = SFX_DUCKS;
    await Promise.all(SFX_IDS.map(async (id) => {
      try {
        this.sfxBuffers.set(id, await resolveAudio(`placeholder:sfx/${id}`));
      } catch { /* missing recipe: stays silent */ }
    }));
  }

  private applyVolumes(): void {
    const p = this.prefs;
    if (!this.ctx || !p) return;
    const t = this.ctx.currentTime;
    const set = (g: GainNode, v: number) => {
      g.gain.cancelScheduledValues(t);
      g.gain.setTargetAtTime(v, t, 0.03);
    };
    set(this.master, p.masterMuted ? 0 : p.master);
    set(this.music, p.musicMuted ? 0 : p.music);
    set(this.sfx, p.sfxMuted ? 0 : p.sfx);
  }

  /** Volumes from prefs (the prefs store calls this automatically; exposed for Settings previews). */
  setVolumes(v: Partial<Pick<Prefs["audio"], "master" | "music" | "sfx">>): void {
    this.prefs = { ...(this.prefs ?? { masterMuted: false, musicMuted: false, sfxMuted: false, master: 0.8, music: 0.6, sfx: 0.8, duckMusic: true }), ...v };
    this.applyVolumes();
  }

  mute(m: Partial<Pick<Prefs["audio"], "masterMuted" | "musicMuted" | "sfxMuted">>): void {
    this.prefs = { ...(this.prefs ?? { masterMuted: false, musicMuted: false, sfxMuted: false, master: 0.8, music: 0.6, sfx: 0.8, duckMusic: true }), ...m };
    this.applyVolumes();
  }

  playSfx(id: SfxId): void {
    if (!this.ctx || !this.state.unlocked) return;
    const buf = this.sfxBuffers.get(id);
    if (!buf) {
      void resolveAudio(`placeholder:sfx/${id}`).then((b) => this.sfxBuffers.set(id, b)).catch(() => {});
      return;
    }
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.connect(this.sfx);
    src.start();
    if (ducks.has(id)) this.duck();
  }

  /** Stings: music to 40 %, 600 ms release (MUS-03). */
  duck(): void {
    if (!this.ctx || this.prefs?.duckMusic === false) return;
    const g = this.duckNode.gain;
    const t = this.ctx.currentTime;
    g.cancelScheduledValues(t);
    g.setValueAtTime(g.value, t);
    g.linearRampToValueAtTime(DUCK_LEVEL, t + DUCK_ATTACK);
    g.setValueAtTime(DUCK_LEVEL, t + DUCK_ATTACK + DUCK_HOLD);
    g.linearRampToValueAtTime(1, t + DUCK_ATTACK + DUCK_HOLD + DUCK_RELEASE);
  }

  /** Equal-power crossfade to `url` (≤ 2 s, MUS-02); null = silence. Same URL = no restart. */
  setMusic(url: string | null, opts: MusicOpts = {}): void {
    this.want = { url, opts };
    if (url && this.deck?.url === url) {
      if (opts.label && this.state.track?.label !== opts.label) this.set({ track: { ...this.state.track!, label: opts.label } });
      return;
    }
    const token = ++this.musicToken;
    const fade = Math.min(MAX_CROSSFADE, opts.crossfadeMs ?? 1500) / 1000;
    this.set({ track: url ? { url, label: opts.label ?? "", procedural: isProceduralAudio(url) } : null, loading: !!url });
    if (!this.ctx || !this.state.unlocked) return;
    const old = this.deck;
    this.deck = null;
    if (old) this.fadeOut(old, fade);
    if (!url) {
      this.set({ loading: false });
      return;
    }
    resolveAudio(url).then((buf) => {
      if (token !== this.musicToken || !this.ctx) return;
      const ctx = this.ctx;
      const gain = ctx.createGain();
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.loop = true;
      src.connect(gain).connect(this.music);
      const t = ctx.currentTime;
      const peak = opts.gainDb ? Math.pow(10, opts.gainDb / 20) : 1;
      gain.gain.setValueAtTime(0, t);
      if (fade > RAMP) gain.gain.setValueCurveAtTime(equalPower(true, peak), t, fade);
      else gain.gain.linearRampToValueAtTime(peak, t + RAMP);
      src.start(t);
      this.deck = { src, gain, url };
      this.set({ loading: false });
    }).catch((err) => {
      if (token === this.musicToken) this.set({ loading: false });
      console.warn("[audio] music failed", url, err);
    });
  }

  private fadeOut(d: Deck, fade: number): void {
    if (!this.ctx) return;
    const t = this.ctx.currentTime;
    const g = d.gain.gain;
    const from = Math.max(0.0001, g.value);
    g.cancelScheduledValues(t);
    if (fade > RAMP) g.setValueCurveAtTime(equalPower(false, from), t, fade);
    else g.linearRampToValueAtTime(0, t + RAMP);
    try {
      d.src.stop(t + Math.max(fade, RAMP) + 0.02);
    } catch { /* already stopped */ }
  }
}

function equalPower(up: boolean, peak: number, n = 32): Float32Array {
  const c = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const x = i / (n - 1);
    c[i] = peak * (up ? Math.sin((x * Math.PI) / 2) : Math.cos((x * Math.PI) / 2));
  }
  return c;
}

/** The one engine (README §3.6). */
export const audio = new AudioEngine();
export type { AudioEngine };
export type { SfxId };
