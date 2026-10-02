// Particle field on a <canvas>, driven by the ONE global ticker (R12): no React state, no per-field rAF.
// A field subscribes to the ticker only while it has live particles or emitters, so idle stages cost nothing.
// Owner: VMD.
import { onTick } from "../ticker";

export type ParticleKind = "sparkle" | "streak" | "glyph" | "spark" | "puff" | "dot" | "ring";

export interface Particle {
  kind: ParticleKind;
  x: number;
  y: number;
  vx: number;
  vy: number;
  /** Acceleration (px/s²). */
  ax: number;
  ay: number;
  /** Velocity damping per second (0 = none, 3 = strong). */
  drag: number;
  life: number;
  age: number;
  size: number;
  /** Size multiplier at end of life (default 1). */
  grow: number;
  rot: number;
  vr: number;
  color: string;
  alpha: number;
  /** Fraction of life spent fading in. */
  fadeIn: number;
  /** Twinkle: alpha follows a sine bump instead of a linear fade. */
  bump?: boolean;
  text?: string;
  font?: string;
  delay: number;
}

export type ParticleInit = Partial<Particle> & Pick<Particle, "kind" | "x" | "y" | "life">;

export interface Emitter {
  /** ms until the next spawn (called after each spawn). */
  next(): number;
  spawn(field: ParticleField): void;
  /** Spawn immediately on start. */
  eager?: boolean;
}

interface EmitterState {
  e: Emitter;
  wait: number;
}

const DEFAULTS: Omit<Particle, "kind" | "x" | "y" | "life"> = {
  vx: 0, vy: 0, ax: 0, ay: 0, drag: 0, age: 0, size: 8, grow: 1, rot: 0, vr: 0,
  color: "#F5F2EA", alpha: 1, fadeIn: 0.12, delay: 0,
};

export class ParticleField {
  readonly canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D | null;
  private parts: Particle[] = [];
  private emitters = new Set<EmitterState>();
  private unsub: (() => void) | null = null;
  private dpr = 1;
  width = 0;
  height = 0;
  /** Hard cap so a runaway emitter can never tank a frame. */
  max = 240;

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.resize();
  }

  /** Match the backing store to the CSS size (call on resize). */
  resize(): void {
    const r = this.canvas.getBoundingClientRect();
    this.dpr = Math.min(2, typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1);
    this.width = Math.max(1, Math.round(r.width));
    this.height = Math.max(1, Math.round(r.height));
    this.canvas.width = Math.round(this.width * this.dpr);
    this.canvas.height = Math.round(this.height * this.dpr);
  }

  /** Read a CSS custom property as resolved at the canvas (follows PaletteScope). */
  cssVar(name: string, fallback: string): string {
    const v = getComputedStyle(this.canvas).getPropertyValue(name).trim();
    return v || fallback;
  }

  add(init: ParticleInit): void {
    if (this.parts.length >= this.max) return;
    this.parts.push({ ...DEFAULTS, ...init });
    this.wake();
  }

  /** Start an emitter; returns a stop function. */
  emit(e: Emitter): () => void {
    const st: EmitterState = { e, wait: e.eager ? 0 : e.next() };
    this.emitters.add(st);
    this.wake();
    return () => {
      this.emitters.delete(st);
    };
  }

  clear(): void {
    this.parts = [];
    this.emitters.clear();
    this.draw();
    this.sleep();
  }

  destroy(): void {
    this.clear();
    this.ctx = null;
  }

  get alive(): number {
    return this.parts.length;
  }

  private wake(): void {
    if (!this.unsub) this.unsub = onTick((dt) => this.step(dt));
  }

  private sleep(): void {
    this.unsub?.();
    this.unsub = null;
  }

  private step(dtMs: number): void {
    const dt = dtMs / 1000;
    for (const st of this.emitters) {
      st.wait -= dtMs;
      let guard = 0;
      while (st.wait <= 0 && guard++ < 8) {
        st.e.spawn(this);
        st.wait += Math.max(16, st.e.next());
      }
    }
    const next: Particle[] = [];
    for (const p of this.parts) {
      if (p.delay > 0) {
        p.delay -= dtMs;
        next.push(p);
        continue;
      }
      p.age += dtMs;
      if (p.age >= p.life) continue;
      const damp = p.drag ? Math.exp(-p.drag * dt) : 1;
      p.vx = (p.vx + p.ax * dt) * damp;
      p.vy = (p.vy + p.ay * dt) * damp;
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.rot += p.vr * dt;
      next.push(p);
    }
    this.parts = next;
    this.draw();
    if (!this.parts.length && !this.emitters.size) this.sleep();
  }

  private draw(): void {
    const c = this.ctx;
    if (!c) return;
    c.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    c.clearRect(0, 0, this.width, this.height);
    for (const p of this.parts) {
      if (p.delay > 0) continue;
      const t = p.age / p.life;
      let a: number;
      if (p.bump) a = Math.sin(Math.PI * t);
      else a = (p.fadeIn > 0 ? Math.min(1, t / p.fadeIn) : 1) * (1 - Math.pow(Math.max(0, (t - p.fadeIn) / (1 - p.fadeIn)), 2));
      a *= p.alpha;
      if (a <= 0.004) continue;
      const size = p.size * (1 + (p.grow - 1) * t);
      c.globalAlpha = a;
      c.save();
      c.translate(p.x, p.y);
      if (p.rot) c.rotate(p.rot);
      drawShape(c, p, size);
      c.restore();
    }
    c.globalAlpha = 1;
  }
}

function drawShape(c: CanvasRenderingContext2D, p: Particle, s: number): void {
  switch (p.kind) {
    case "sparkle": {
      // four-point star: M0,-s C k,-k k,-k s,0 … (VMD §2.5), slightly fuller so it reads at speed
      const k = s * 0.2;
      c.beginPath();
      c.moveTo(0, -s);
      c.bezierCurveTo(k, -k, k, -k, s, 0);
      c.bezierCurveTo(k, k, k, k, 0, s);
      c.bezierCurveTo(-k, k, -k, k, -s, 0);
      c.bezierCurveTo(-k, -k, -k, -k, 0, -s);
      c.fillStyle = p.color;
      c.fill();
      break;
    }
    case "streak": {
      c.strokeStyle = p.color;
      c.lineWidth = 1.5;
      c.lineCap = "round";
      c.beginPath();
      c.moveTo(0, -s / 2);
      c.lineTo(0, s / 2);
      c.stroke();
      break;
    }
    case "spark": {
      c.fillStyle = p.color;
      c.beginPath();
      c.moveTo(0, -s);
      c.lineTo(s * 0.35, 0);
      c.lineTo(0, s);
      c.lineTo(-s * 0.35, 0);
      c.closePath();
      c.fill();
      break;
    }
    case "puff": {
      c.fillStyle = p.color;
      c.beginPath();
      c.arc(-s * 0.35, 0, s * 0.55, 0, Math.PI * 2);
      c.arc(s * 0.3, -s * 0.15, s * 0.65, 0, Math.PI * 2);
      c.arc(s * 0.05, s * 0.3, s * 0.5, 0, Math.PI * 2);
      c.fill();
      break;
    }
    case "ring": {
      c.strokeStyle = p.color;
      c.lineWidth = Math.max(2, s * 0.06 + 3);
      c.beginPath();
      c.arc(0, 0, s, 0, Math.PI * 2);
      c.stroke();
      break;
    }
    case "glyph": {
      c.fillStyle = p.color;
      c.font = `${Math.round(s)}px ${p.font ?? '"Anton", Impact, sans-serif'}`;
      c.textAlign = "center";
      c.textBaseline = "middle";
      c.lineWidth = Math.max(2, s * 0.14);
      c.strokeStyle = "rgba(11,11,15,0.85)";
      c.lineJoin = "round";
      c.strokeText(p.text ?? "", 0, 0);
      c.fillText(p.text ?? "", 0, 0);
      break;
    }
    case "dot":
    default: {
      c.fillStyle = p.color;
      c.beginPath();
      c.arc(0, 0, s, 0, Math.PI * 2);
      c.fill();
    }
  }
}
