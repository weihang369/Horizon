// Route & palette transitions (spec §3.2, VMD paper §2.4). Owner: VMD.
// Imperative WAAPI on a single fixed host (TransitionLayer); transform + opacity only.
// A new route transition supersedes the previous one (its onCover is dropped, R3).
import { DUR, EASE, FLASH_PEAK, STAGGER } from "./tokens";
import { getMotionPrefs } from "./prefs";

export type TransitionKind = "slash" | "slash-back" | "shatter" | "flood" | "fade" | "none";

export interface TransitionOpts {
  origin?: { x: number; y: number };
  sourceEl?: HTMLElement | null;
  /** Main colour (CSS colour or var()). Defaults: slash → var(--c-primary), flood → var(--c-primary). */
  color?: string;
  /** Called exactly once at the cover point (never if cancelled before it). */
  onCover: () => void;
}

export interface TransitionHandle {
  cancel(): void;
  done: Promise<void>;
}

// ── Host ─────────────────────────────────────────────────────────────────────
let host: HTMLElement | null = null;
let fallbackHost: HTMLElement | null = null;

/** Called by <TransitionLayer/>. */
export function registerTransitionHost(el: HTMLElement | null): void {
  host = el;
}

function getHost(): HTMLElement {
  if (host && host.isConnected) return host;
  if (!fallbackHost || !fallbackHost.isConnected) {
    fallbackHost = document.createElement("div");
    fallbackHost.setAttribute("aria-hidden", "true");
    Object.assign(fallbackHost.style, {
      position: "fixed", inset: "0", pointerEvents: "none", zIndex: "100", overflow: "hidden", contain: "strict",
    } satisfies Partial<CSSStyleDeclaration>);
    document.body.appendChild(fallbackHost);
  }
  return fallbackHost;
}

function el(style: Partial<CSSStyleDeclaration>, parent: HTMLElement): HTMLDivElement {
  const d = document.createElement("div");
  Object.assign(d.style, { position: "absolute", willChange: "transform, opacity", ...style });
  parent.appendChild(d);
  return d;
}

// ── Runner ───────────────────────────────────────────────────────────────────
interface Running {
  nodes: HTMLElement[];
  anims: Animation[];
  timers: number[];
  covered: boolean;
  cancelled: boolean;
  resolve: () => void;
}

let currentRoute: { cancel(): void } | null = null;

function makeRunner(onCover: () => void): { r: Running; handle: TransitionHandle; cover: (atMs: number) => void; finish: (atMs: number) => void } {
  let resolve!: () => void;
  const done = new Promise<void>((res) => (resolve = res));
  const r: Running = { nodes: [], anims: [], timers: [], covered: false, cancelled: false, resolve };
  const cleanup = () => {
    r.timers.forEach((t) => clearTimeout(t));
    r.anims.forEach((a) => a.cancel());
    r.nodes.forEach((n) => n.remove());
    r.nodes = [];
    r.anims = [];
  };
  const handle: TransitionHandle = {
    cancel() {
      if (r.cancelled) return;
      r.cancelled = true;
      cleanup();
      resolve();
    },
    done,
  };
  return {
    r,
    handle,
    cover(atMs) {
      const fire = () => {
        if (r.cancelled || r.covered) return;
        r.covered = true;
        onCover();
      };
      if (atMs <= 0) fire();
      else r.timers.push(window.setTimeout(fire, atMs));
    },
    finish(atMs) {
      r.timers.push(
        window.setTimeout(() => {
          if (r.cancelled) return;
          cleanup();
          resolve();
        }, atMs),
      );
    },
  };
}

/** Run a transition. Reduced motion turns every kind (except none) into a 160 ms fade. */
export function runTransition(kind: TransitionKind, opts: TransitionOpts): TransitionHandle {
  const isRoute = kind !== "flood";
  if (isRoute && currentRoute) currentRoute.cancel();

  if (kind === "none" || typeof document === "undefined") {
    opts.onCover();
    return { cancel() {}, done: Promise.resolve() };
  }
  const prefs = getMotionPrefs();
  const effective: TransitionKind = prefs.reduced ? "fade" : kind === "shatter" && !opts.sourceEl ? "slash" : kind;

  const run = makeRunner(opts.onCover);
  const parent = getHost();
  const add = (n: HTMLElement, a: Animation) => {
    run.r.nodes.push(n);
    run.r.anims.push(a);
  };

  switch (effective) {
    case "slash":
    case "slash-back": {
      const dir = effective === "slash" ? 1 : -1;
      const color = opts.color ?? "var(--c-primary)";
      // Pane A (covers): 160vw wide band, skewed (no text inside, so skew is fine here).
      // Leading paper hairline (box-shadow on the travel side) sells the cut.
      const a = el({
        top: "-10vh", height: "120vh", width: "170vw", left: "-35vw", background: color,
        boxShadow: `${dir * 14}px 0 0 0 var(--paper-50)`,
      }, parent);
      const b = el({ top: "-10vh", height: "120vh", width: "45vw", left: "0", background: "var(--ink-900)" }, parent);
      parent.insertBefore(b, a);
      const sk = `skewX(${-14 * dir}deg)`;
      const animA = a.animate(
        [
          { transform: `translateX(${-180 * dir}vw) ${sk}`, easing: EASE.wipe },
          { transform: `translateX(0) ${sk}`, offset: 0.48 },
          { transform: `translateX(0) ${sk}`, offset: 0.56, easing: EASE.wipe },
          { transform: `translateX(${170 * dir}vw) ${sk}` },
        ],
        { duration: 450, fill: "both" },
      );
      const animB = b.animate(
        [
          { transform: `translateX(${-80 * dir}vw) ${sk}` },
          { transform: `translateX(${160 * dir}vw) ${sk}` },
        ],
        { duration: 330, delay: 120, easing: EASE.wipe, fill: "both" },
      );
      add(a, animA);
      add(b, animB);
      run.cover(230);
      run.finish(470);
      break;
    }
    case "shatter": {
      const src = opts.sourceEl as HTMLElement;
      const rect = src.getBoundingClientRect();
      const veil = el({ inset: "0", background: "var(--c-stage, var(--ink-900))" }, parent);
      const vA = veil.animate([{ opacity: 1 }, { opacity: 1, offset: 150 / 550 }, { opacity: 0 }], {
        duration: 550, easing: EASE.out, fill: "both",
      });
      add(veil, vA);
      const w = src.offsetWidth || rect.width;
      const h = src.offsetHeight || rect.height;
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const ox = clamp((opts.origin?.x ?? cx) - (cx - w / 2), w * 0.15, w * 0.85);
      const oy = clamp((opts.origin?.y ?? cy) - (cy - h / 2), h * 0.15, h * 0.85);
      const shards = shardPolygons(w, h, ox, oy, 6);
      const srcTransform = getComputedStyle(src).transform;
      shards.forEach((poly, i) => {
        const wrap = el({ left: `${cx - w / 2}px`, top: `${cy - h / 2}px`, width: `${w}px`, height: `${h}px` }, parent);
        const clone = src.cloneNode(true) as HTMLElement;
        clone.removeAttribute("id");
        clone.setAttribute("aria-hidden", "true");
        Object.assign(clone.style, {
          position: "absolute", inset: "0", width: `${w}px`, height: `${h}px`, margin: "0",
          transform: srcTransform === "none" ? "" : srcTransform, pointerEvents: "none",
        });
        wrap.appendChild(clone);
        wrap.style.clipPath = `polygon(${poly.points.map(([x, y]) => `${x.toFixed(1)}px ${y.toFixed(1)}px`).join(",")})`;
        wrap.style.transformOrigin = `${poly.cx}px ${poly.cy}px`;
        const dist = 120 + seeded(i * 7 + 1) * 140;
        const rot = (8 + seeded(i * 13 + 5) * 17) * (seeded(i + 3) > 0.5 ? 1 : -1);
        const dx = Math.cos(poly.angle) * dist;
        const dy = Math.sin(poly.angle) * dist;
        // Crack (shards jump apart ~8 % in 70 ms), then accelerate out; fade is back-loaded.
        const anim = wrap.animate(
          [
            { transform: "translate(0,0) rotate(0deg) scale(1)", opacity: 1, easing: EASE.out },
            { transform: `translate(${dx * 0.08}px, ${dy * 0.08}px) rotate(${rot * 0.15}deg) scale(1.02)`, opacity: 1, offset: 0.13, easing: "cubic-bezier(.4,0,.7,.4)" },
            { transform: `translate(${dx * 0.55}px, ${dy * 0.55}px) rotate(${rot * 0.6}deg) scale(0.98)`, opacity: 0.9, offset: 0.62, easing: EASE.in },
            { transform: `translate(${dx}px, ${dy}px) rotate(${rot}deg) scale(0.94)`, opacity: 0 },
          ],
          { duration: 550, delay: i * STAGGER.shard, fill: "both" },
        );
        add(wrap, anim);
      });
      run.cover(0);
      run.finish(550 + shards.length * STAGGER.shard + 20);
      break;
    }
    case "flood": {
      const peak = FLASH_PEAK[prefs.flash];
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const x = opts.origin?.x ?? vw / 2;
      const y = opts.origin?.y ?? vh / 2;
      if (peak === 0) {
        // Flash "off": a soft stage-colour veil, snap at its peak.
        const veil = el({ inset: "0", background: "var(--c-stage)", opacity: "0" }, parent);
        const a = veil.animate([{ opacity: 0 }, { opacity: 0.6 }, { opacity: 0 }], { duration: 320, easing: "ease-in-out", fill: "both" });
        add(veil, a);
        run.cover(160);
        run.finish(340);
        break;
      }
      const R = Math.hypot(Math.max(x, vw - x), Math.max(y, vh - y));
      const c = el(
        {
          left: `${x - R}px`, top: `${y - R}px`, width: `${R * 2}px`, height: `${R * 2}px`,
          borderRadius: "50%", background: opts.color ?? "var(--c-primary)",
        },
        parent,
      );
      const a = c.animate(
        [
          { transform: "scale(0)", opacity: peak, easing: EASE.out },
          { transform: "scale(1)", opacity: peak, offset: 0.5 },
          { transform: "scale(1)", opacity: peak, offset: 0.625 },
          { transform: "scale(1)", opacity: 0 },
        ],
        { duration: DUR.slow, fill: "both" },
      );
      add(c, a);
      run.cover(200);
      run.finish(DUR.slow + 20);
      break;
    }
    case "fade":
    default: {
      const half = prefs.reduced ? DUR.reduced / 2 : 100;
      const veil = el({ inset: "0", background: "var(--ink-900)", opacity: "0" }, parent);
      const a = veil.animate([{ opacity: 0 }, { opacity: 1 }, { opacity: 0 }], { duration: half * 2, easing: "linear", fill: "both" });
      add(veil, a);
      run.cover(half);
      run.finish(half * 2 + 20);
      break;
    }
  }

  if (isRoute) {
    const token = run.handle;
    currentRoute = token;
    void token.done.then(() => {
      if (currentRoute === token) currentRoute = null;
    });
  }
  return run.handle;
}

// ── Shatter geometry ─────────────────────────────────────────────────────────
function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

function seeded(n: number): number {
  const x = Math.sin(n * 12.9898 + 78.233) * 43758.5453;
  return x - Math.floor(x);
}

interface Shard {
  points: [number, number][];
  angle: number;
  cx: number;
  cy: number;
}

/** Split a w×h box into n shards radiating from (ox, oy). Exported for tests. */
export function shardPolygons(w: number, h: number, ox: number, oy: number, n = 6): Shard[] {
  const TAU = Math.PI * 2;
  const base = seeded(w + h) * TAU;
  const angles = Array.from({ length: n }, (_, i) => base + (i / n) * TAU + (seeded(i * 3.1) - 0.5) * 0.4);
  const corners: [number, number][] = [[0, 0], [w, 0], [w, h], [0, h]];
  const norm = (a: number) => ((a % TAU) + TAU) % TAU;
  const hit = (a: number): [number, number] => {
    const dx = Math.cos(a);
    const dy = Math.sin(a);
    const ts: number[] = [];
    if (dx > 1e-6) ts.push((w - ox) / dx);
    if (dx < -1e-6) ts.push(-ox / dx);
    if (dy > 1e-6) ts.push((h - oy) / dy);
    if (dy < -1e-6) ts.push(-oy / dy);
    const t = Math.min(...ts);
    return [ox + dx * t, oy + dy * t];
  };
  return angles.map((a0, i) => {
    const a1 = angles[(i + 1) % n] + (i === n - 1 ? TAU : 0);
    const span = a1 - a0;
    const between = corners
      .map((c) => ({ c, d: norm(Math.atan2(c[1] - oy, c[0] - ox) - a0) }))
      .filter((x) => x.d > 0 && x.d < span)
      .sort((p, q) => p.d - q.d)
      .map((x) => x.c);
    const pts: [number, number][] = [[ox, oy], hit(a0), ...between, hit(a1)];
    const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length;
    const cy = pts.reduce((s, p) => s + p[1], 0) / pts.length;
    return { points: pts, angle: (a0 + a1) / 2, cx, cy };
  });
}
