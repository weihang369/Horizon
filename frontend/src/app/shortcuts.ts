// Focus-aware, overlay-scoped shortcuts (README §3.3, APP-10, doc 03 §6). Owner: EE.
// Single-key combos never fire while typing (isTypingTarget) unless `allowInInput`. A shortcut registered inside a
// layer fires only while that layer is the top blocking layer; screen shortcuts are muted under modals/ceremonies.
import { createContext, useContext, useEffect, useRef } from "react";
import { ui } from "../stores/ui";

export interface ShortcutOpts {
  allowInInput?: boolean;
  when?: () => boolean;
  /** Fire regardless of open layers (dev tools). Additive. */
  global?: boolean;
}

interface Entry { combo: string; handler: (e: KeyboardEvent) => void; opts: ShortcutOpts; layerKey: number; order: number }

/** Layer key of the nearest LayerStack layer (0 = the screen). Provided by LayerStack. */
export const LayerKeyContext = createContext(0);

const entries = new Set<Entry>();
let order = 0;
let installed = false;

export function isTypingTarget(el: EventTarget | Element | null | undefined): boolean {
  if (!el || !(el instanceof HTMLElement)) return false;
  if (el.isContentEditable) return true;
  const tag = el.tagName;
  if (tag === "TEXTAREA" || tag === "SELECT") return true;
  if (tag !== "INPUT") return false;
  const type = (el as HTMLInputElement).type;
  return !["button", "checkbox", "radio", "range", "submit", "reset", "color", "file", "image"].includes(type);
}

/** "Ctrl+Shift+D" → "ctrl+shift+d"; aliases: esc, space, mod (= ctrl on Windows/Linux, meta on Mac). */
export function normalizeCombo(combo: string): string {
  const isMac = typeof navigator !== "undefined" && /Mac/i.test(navigator.platform);
  const parts = combo.toLowerCase().split("+").map((p) => p.trim()).filter(Boolean);
  const key = parts.pop() ?? "";
  const mods = new Set(parts.map((m) => (m === "mod" ? (isMac ? "meta" : "ctrl") : m === "cmd" ? "meta" : m === "option" ? "alt" : m)));
  const k = key === "esc" ? "escape" : key === " " ? "space" : key === "right" ? "arrowright" : key === "left" ? "arrowleft" : key;
  return [...["ctrl", "alt", "shift", "meta"].filter((m) => mods.has(m)), k].join("+");
}

export function comboOf(e: KeyboardEvent): string {
  let key = e.key.toLowerCase();
  if (key === " ") key = "space";
  else if (key === "esc") key = "escape";
  const hasCmd = e.ctrlKey || e.altKey || e.metaKey;
  if (hasCmd && /^Key[A-Z]$/.test(e.code)) key = e.code.slice(3).toLowerCase();
  if (hasCmd && /^Digit\d$/.test(e.code)) key = e.code.slice(5);
  const printableSymbol = key.length === 1 && !/[a-z0-9]/.test(key);
  const mods = [e.ctrlKey && "ctrl", e.altKey && "alt", e.shiftKey && !printableSymbol && "shift", e.metaKey && "meta"].filter(Boolean);
  return [...mods, key].join("+");
}

function topBlockingKey(): number {
  const layers = ui.getState().layers;
  for (let i = layers.length - 1; i >= 0; i--) if (layers[i].kind === "modal" || layers[i].kind === "ceremony") return layers[i].key;
  return 0;
}

function onKey(e: KeyboardEvent): void {
  if (e.defaultPrevented || e.isComposing) return;
  const combo = comboOf(e);
  const single = !e.ctrlKey && !e.altKey && !e.metaKey;
  const typing = isTypingTarget(e.target);
  const top = topBlockingKey();
  const list = [...entries].filter((x) => x.combo === combo).sort((a, b) => b.order - a.order);
  for (const x of list) {
    if (single && typing && !x.opts.allowInInput) continue;
    if (!x.opts.global && x.layerKey !== top && !(top === 0 && x.layerKey === 0)) {
      // Popover/drawer layers count as the screen for scoping (they don't block).
      const layers = ui.getState().layers;
      const own = layers.find((l) => l.key === x.layerKey);
      if (!(own && (own.kind === "drawer" || own.kind === "popover") && top === 0)) continue;
    }
    if (x.opts.when && !x.opts.when()) continue;
    e.preventDefault();
    x.handler(e);
    return;
  }
}

function install(): void {
  if (installed || typeof window === "undefined") return;
  installed = true;
  window.addEventListener("keydown", onKey);
}

/** Register a keyboard shortcut for the lifetime of the component. */
export function useShortcut(combo: string, handler: (e: KeyboardEvent) => void, opts: ShortcutOpts = {}): void {
  const layerKey = useContext(LayerKeyContext);
  const h = useRef(handler);
  const o = useRef(opts);
  h.current = handler;
  o.current = opts;
  useEffect(() => {
    install();
    const entry: Entry = {
      combo: normalizeCombo(combo),
      handler: (e) => h.current(e),
      get opts() { return o.current; },
      layerKey,
      order: order++,
    };
    entries.add(entry);
    return () => {
      entries.delete(entry);
    };
  }, [combo, layerKey]);
}

/** All registered combos (for the O20 sheet / debugging). */
export const registeredShortcuts = (): string[] => [...new Set([...entries].map((e) => e.combo))];
