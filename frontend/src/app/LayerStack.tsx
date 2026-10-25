// LayerStack (R4, UXA D1): renders the ui store's layers with central Esc order and focus trap/restore.
// Esc: popover → dock expansion → modal → drawer → blur text field → pause menu (O01; Esc again resumes).
import { Suspense, useEffect, useLayoutEffect, useRef } from "react";
import type { ComponentType, ReactNode } from "react";
import { getRoute } from "../router";
import { ui, useUi } from "../stores/ui";
import type { Layer } from "../stores/ui";
import { closeOverlay, openOverlay } from "./layers";
import { OVERLAYS } from "./overlays";
import type { AnchorRect, OverlayComponentProps, OverlayId } from "./overlayTypes";
import { isTypingTarget, LayerKeyContext } from "./shortcuts";
import s from "./App.module.css";

const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

function topOf(layers: Layer[], kind: Layer["kind"]): Layer | undefined {
  for (let i = layers.length - 1; i >= 0; i--) if (layers[i].kind === kind) return layers[i];
  return undefined;
}

/** Central Esc router. Installed once by <LayerStack/>. */
export function handleEscape(e: KeyboardEvent): void {
  if (e.key !== "Escape" || e.defaultPrevented) return;
  const st = ui.getState();
  const done = () => {
    e.preventDefault();
    e.stopPropagation();
  };
  const pop = topOf(st.layers, "popover");
  if (pop) return done(), closeOverlay(pop.key);
  if (st.dockExpansion) return done(), closeOverlay("O12");
  const modal = topOf(st.layers, "modal");
  if (modal) return done(), closeOverlay(modal.key);
  const drawer = topOf(st.layers, "drawer");
  if (drawer) return done(), closeOverlay(drawer.key);
  const active = document.activeElement;
  if (isTypingTarget(active)) return done(), (active as HTMLElement).blur();
  if (topOf(st.layers, "ceremony")) return; // the conductor skips ceremonies on any key
  const r = getRoute().name;
  if (r === "title" || r === "onboarding") return;
  done();
  openOverlay("O01");
}

function FocusTrap({ active, children }: { active: boolean; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || !active) return;
    const first = el.querySelector<HTMLElement>("[autofocus]") ?? el.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? el).focus({ preventScroll: true });
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const items = [...el.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((x) => x.offsetParent !== null || x === document.activeElement);
      if (!items.length) {
        e.preventDefault();
        return;
      }
      const a = items[0];
      const z = items[items.length - 1];
      if (e.shiftKey && (document.activeElement === a || !el.contains(document.activeElement))) {
        e.preventDefault();
        z.focus();
      } else if (!e.shiftKey && (document.activeElement === z || !el.contains(document.activeElement))) {
        e.preventDefault();
        a.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [active]);
  return <div ref={ref} tabIndex={-1} style={{ outline: "none", display: "contents" }}>{children}</div>;
}

function popoverStyle(anchor?: AnchorRect): React.CSSProperties | undefined {
  if (!anchor) return undefined;
  const below = anchor.y + anchor.height + 8;
  const fitsBelow = typeof window === "undefined" || below < window.innerHeight - 200;
  return fitsBelow
    ? { left: Math.max(8, anchor.x), top: below }
    : { left: Math.max(8, anchor.x), bottom: (typeof window === "undefined" ? 0 : window.innerHeight) - anchor.y + 8 };
}

/** An anchored popover kept inside the window (U-86): `popoverStyle` places it from a guessed height, so once it has
 * rendered, and whenever its content changes size (the portrait menu's 7 faces), it moves back in by what overflows. */
function AnchoredPopover({ anchor, id, children }: { anchor: AnchorRect; id: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const fit = () => {
      el.style.translate = "";
      const r = el.getBoundingClientRect();
      const dx = Math.min(0, window.innerWidth - 8 - r.right);
      let dy = Math.min(0, window.innerHeight - 8 - r.bottom);
      if (r.top + dy < 8) dy = 8 - r.top;
      if (dx || dy) el.style.translate = `${dx}px ${dy}px`;
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    return () => ro.disconnect();
  }, [anchor]);
  return <div ref={ref} className={s.popover} style={popoverStyle(anchor)} data-layer={id}>{children}</div>;
}

function LayerView({ layer, trap }: { layer: Layer; trap: boolean }) {
  const C = OVERLAYS[layer.id as OverlayId].component as unknown as ComponentType<OverlayComponentProps<OverlayId>>;
  const close = () => closeOverlay(layer.key);
  const body = (
    <LayerKeyContext.Provider value={layer.key}>
      <Suspense fallback={null}>
        <C {...(layer.props as OverlayComponentProps<OverlayId>)} close={close} layerKey={layer.key} />
      </Suspense>
    </LayerKeyContext.Provider>
  );
  switch (layer.kind) {
    case "modal":
      return (
        <div className={s.backdrop} data-layer={layer.id} onMouseDown={(e) => { if (e.target === e.currentTarget) close(); }}>
          <FocusTrap active={trap}>{body}</FocusTrap>
        </div>
      );
    case "drawer":
      return <div className={s.drawerSlot} data-layer={layer.id}>{body}</div>;
    case "popover": {
      const anchor = (layer.props as { anchor?: AnchorRect }).anchor;
      return (
        <>
          <div style={{ position: "fixed", inset: 0, zIndex: "calc(var(--z-modal) + 4)" }} onMouseDown={close} aria-hidden="true" />
          {anchor
            ? <AnchoredPopover anchor={anchor} id={layer.id}>{body}</AnchoredPopover>
            : <div className={`${s.popover} ${s.popoverCentered}`} data-layer={layer.id}>{body}</div>}
        </>
      );
    }
    case "ceremony":
      return <div className={s.ceremony} data-layer={layer.id}>{body}</div>;
    default:
      return null;
  }
}

export function LayerStack() {
  const layers = useUi((u) => u.layers);
  useEffect(() => {
    window.addEventListener("keydown", handleEscape, true);
    return () => window.removeEventListener("keydown", handleEscape, true);
  }, []);
  const topModal = topOf(layers, "modal");
  return (
    <>
      {layers.map((l) => <LayerView key={l.key} layer={l} trap={l === topModal} />)}
    </>
  );
}
