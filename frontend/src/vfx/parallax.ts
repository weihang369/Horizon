// Cursor parallax (doc 04 §4 "idle life": 6–10 px opposite the cursor). Owner: VMD.
// One pointermove listener + the one global ticker (R12). Elements get `transform: translate3d()`
// written directly; the ticker unsubscribes once every element has settled.
import { onTick } from "./ticker";

interface Entry {
  depth: number;
  x: number;
  y: number;
}

const els = new Map<HTMLElement, Entry>();
let tx = 0;
let ty = 0;
let unsub: (() => void) | null = null;
let listening = false;

function onMove(e: PointerEvent): void {
  tx = (e.clientX / window.innerWidth) * 2 - 1;
  ty = (e.clientY / window.innerHeight) * 2 - 1;
  wake();
}

function wake(): void {
  if (!unsub && els.size) unsub = onTick(step);
}

function step(dt: number): void {
  const k = 1 - Math.exp(-dt / 140); // ~140 ms smoothing
  let moving = false;
  els.forEach((en, el) => {
    const gx = -tx * en.depth;
    const gy = -ty * en.depth * 0.6;
    en.x += (gx - en.x) * k;
    en.y += (gy - en.y) * k;
    if (Math.abs(gx - en.x) > 0.02 || Math.abs(gy - en.y) > 0.02) moving = true;
    el.style.transform = `translate3d(${en.x.toFixed(2)}px, ${en.y.toFixed(2)}px, 0)`;
  });
  if (!moving) {
    unsub?.();
    unsub = null;
  }
}

/** Register an element for parallax. depth = max offset in px (6–10). Returns an unregister function. */
export function registerParallax(el: HTMLElement, depth = 8): () => void {
  els.set(el, { depth, x: 0, y: 0 });
  if (!listening && typeof window !== "undefined") {
    window.addEventListener("pointermove", onMove, { passive: true });
    listening = true;
  }
  wake();
  return () => {
    els.delete(el);
    el.style.transform = "";
    if (!els.size && listening) {
      window.removeEventListener("pointermove", onMove);
      listening = false;
      unsub?.();
      unsub = null;
    }
  };
}
