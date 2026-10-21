// S03 World Select (WLD-01): a centred rail of tilted world cards (−8°, 40 px overlap), "+ New World" always last.
// Hover/focus straightens to −4° and lifts 12 px with a hover tick; a card shatters into its Hub (README §3.1).
// Owner: Builder A.
import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent, MouseEvent } from "react";
import { openOverlay } from "../../app/layers";
import { useShortcut } from "../../app/shortcuts";
import { audio } from "../../audio/engine";
import { client } from "../../client";
import { useCharacters, useNow, useWorlds } from "../../client/hooks";
import type { World } from "../../contract/types";
import { formatRelative } from "../../domain/format";
import { useMotionPrefs } from "../../motion/prefs";
import { navigate } from "../../router";
import { Button } from "../../ui/Button";
import { Kbd } from "../../ui/Kbd";
import { EmptyState, ErrorTape } from "../../ui/Panels";
import { RansomText } from "../../ui/RansomText";
import { Tape } from "../../ui/Tape";
import { WorldCover } from "../../ui/WorldCover";
import { GearIcon, PlusIcon } from "../../ui/icons";
import { useHouseScreen } from "../shell/house";
import { headUrl } from "./portraitUrls";
import s from "./WorldSelect.module.css";

let lastHover = 0;
export function hoverTick(): void {
  const now = performance.now();
  if (now - lastHover < 90) return;
  lastHover = now;
  audio.playSfx("ui_hover");
}

/** Room left of a paged-to card, past the rail's edge fade (WorldSelect.module.css .rail mask). */
const EDGE = 96;

/** The seed debate replay World Select links to directly (doc 06). */
const FEATURED = { worldId: "wld_seedMeridian", sessionId: "ses_seedDebate4Day" } as const;

export function WorldSelectScreen() {
  useHouseScreen();
  const { data: worlds, loading, error, reload } = useWorlds();
  const rail = useRef<HTMLDivElement>(null);
  const sorted = worlds ? [...worlds].sort((a, b) => Date.parse(b.lastActiveAt) - Date.parse(a.lastActiveAt)) : [];

  const { reduced } = useMotionPrefs();
  const [more, setMore] = useState({ left: false, right: false });
  const measure = useCallback(() => {
    const r = rail.current;
    if (!r) return;
    const left = r.scrollLeft > 4;
    const right = r.scrollLeft + r.clientWidth < r.scrollWidth - 4;
    setMore((m) => (m.left === left && m.right === right ? m : { left, right }));
  }, []);
  useEffect(() => {
    const r = rail.current;
    if (!r) return;
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(r);
    // A vertical wheel scrolls the rail sideways: with many worlds a mouse without a horizontal wheel must still reach
    // them. Native listener, not React's onWheel, which is passive and can't keep the page from eating the gesture.
    const onWheel = (e: WheelEvent) => {
      if (Math.abs(e.deltaY) <= Math.abs(e.deltaX) || r.scrollWidth <= r.clientWidth) return;
      e.preventDefault();
      r.scrollLeft += e.deltaMode === 1 ? e.deltaY * 40 : e.deltaY;
    };
    r.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      ro.disconnect();
      r.removeEventListener("wheel", onWheel);
    };
  }, [measure, loading, sorted.length]);

  /** Scrolls only the rail, never the screen or the page (scrollIntoView would move every scrollable ancestor). */
  const railTo = (left: number) => rail.current?.scrollTo({ left, behavior: reduced ? "auto" : "smooth" });
  const centre = (el: HTMLElement) => {
    const r = rail.current!;
    const a = el.getBoundingClientRect();
    const b = r.getBoundingClientRect();
    railTo(r.scrollLeft + a.left + a.width / 2 - (b.left + b.width / 2));
  };
  /** ◂/▸: about a screen of cards, snapped so a whole card starts at the left edge instead of a cut one. */
  const page = (dir: 1 | -1) => {
    const r = rail.current!;
    const x0 = r.getBoundingClientRect().left - r.scrollLeft;
    const starts = [...r.querySelectorAll<HTMLElement>("[data-card]")].map((x) => x.getBoundingClientRect().left - x0);
    const want = r.scrollLeft + dir * r.clientWidth * 0.75 + EDGE;
    railTo(starts.reduce((a, b) => (Math.abs(b - want) < Math.abs(a - want) ? b : a)) - EDGE);
  };

  // ←/→ (and Home/End) choose a card from anywhere on the screen, not only once a card has focus: after a load or a
  // mouse click focus sits on <body>, and the footer promises the keys work.
  const moveFocus = (key: "arrowright" | "arrowleft" | "home" | "end") => {
    const r = rail.current;
    const items = [...(r?.querySelectorAll<HTMLElement>("[data-card]") ?? [])];
    if (!r || !items.length) return;
    // No card focused, or the focused one was wheeled/paged out of view: start from the first card in view.
    const box = r.getBoundingClientRect();
    const inView = (x: HTMLElement) => {
      const a = x.getBoundingClientRect();
      return a.left + a.width / 2 > box.left && a.left + a.width / 2 < box.right;
    };
    const firstInView = Math.max(0, items.findIndex(inView));
    const focused = items.indexOf(document.activeElement as HTMLElement);
    const i = focused >= 0 && inView(items[focused]) ? focused : -1;
    const next = key === "home" ? 0 : key === "end" ? items.length - 1 : i < 0 ? firstInView : i + (key === "arrowright" ? 1 : -1);
    const el = items[Math.max(0, Math.min(items.length - 1, next))];
    el.focus({ preventScroll: true });
    const a = el.getBoundingClientRect();
    // Picked up in place: no scroll when it's already in view (the −8° tilt overhangs its slot by ~35 px).
    if (i < 0 && key.startsWith("arrow") && a.left >= box.left - 40 && a.right <= box.right + 40) return;
    if (key === "home") railTo(0);
    else if (key === "end") railTo(r.scrollWidth);
    else centre(el);
  };
  useShortcut("arrowright", () => moveFocus("arrowright"));
  useShortcut("arrowleft", () => moveFocus("arrowleft"));
  useShortcut("home", () => moveFocus("home"));
  useShortcut("end", () => moveFocus("end"));

  return (
    <main className={s.screen} data-screen="S03" aria-labelledby="worlds-title">
      <div className={s.backdrop} aria-hidden="true" />
      <header className={s.head}>
        <h1 id="worlds-title" className={s.title}>
          <RansomText text="WORLDS" size="var(--title-size)" tone="mixed" slam staggerMs={40} />
        </h1>
        <p className={s.sub}>Pick a universe. Nothing crosses between them.</p>
        <nav className={s.headNav} aria-label="Shell">
          {worlds?.some((w) => w.id === FEATURED.worldId) && (
            // U2: the strongest feature in one click (otherwise world → hub → Sessions → replay).
            <Button size="sm" onClick={() => navigate({ name: "session", ...FEATURED, replay: true }, { transition: "slash" })}>▶ Watch a 60-second AI debate</Button>
          )}
          <Button variant="ghost" size="sm" onClick={() => navigate({ name: "title" }, { transition: "slash-back" })}>◂ Title</Button>
          <Button variant="ghost" size="sm" onClick={() => navigate({ name: "onboarding", card: 1 })}>How it works</Button>
          <Button variant="ghost" size="sm" icon={<GearIcon />} onClick={() => navigate({ name: "settings", from: "/worlds" })}>Settings</Button>
          <Button variant="ghost" size="sm" onClick={() => openOverlay("O01")}>☰ Menu</Button>
        </nav>
      </header>

      {error && <div className={s.state}><ErrorTape message="Couldn't load your worlds." code={error.code} action={{ label: "Retry", run: reload }} /></div>}

      {!error && !loading && sorted.length === 0 ? (
        <div className={s.state}>
          <EmptyState
            title="No universes yet"
            body="Every story needs a horizon."
            action={{ label: "+ Create world", run: () => openOverlay("O02", {}) }}
          />
          <Button variant="ghost" size="sm" onClick={() => void client.admin.resetDemo()}>Restore demo data</Button>
        </div>
      ) : !error && (
        <div className={s.railWrap}>
          <div ref={rail} className={s.rail} role="list" aria-label="Worlds" data-more-left={more.left || undefined} data-more-right={more.right || undefined} onScroll={measure}>
            {loading
              ? [0, 1].map((i) => <div key={i} role="listitem" className={`${s.card} ${s.skeleton}`} aria-label="Loading world" />)
              : sorted.map((w, i) => <WorldCard key={w.id} world={w} index={i} />)}
            <div role="listitem" className={s.slot} style={{ ["--i" as string]: sorted.length }}>
              <button type="button" data-card className={`${s.card} ${s.newCard}`} onClick={() => openOverlay("O02", {})} onMouseEnter={hoverTick} onFocus={hoverTick}>
                <span className={`${s.face} ${s.newFace}`}>
                  <span className={s.newPlus} aria-hidden="true"><PlusIcon width={56} height={56} /></span>
                  <span className={s.newLabel}>New World</span>
                  <span className={s.newHint}>Name it, pick a cover, tell it who you are.</span>
                </span>
              </button>
            </div>
          </div>
          {/* Many worlds: paging arrows show only while there's more that way (keys and the wheel work too). */}
          {more.left && <button type="button" tabIndex={-1} className={`${s.page} ${s.pagePrev}`} aria-label="Scroll worlds left" onMouseDown={(e) => e.preventDefault()} onClick={() => page(-1)}>◂</button>}
          {more.right && <button type="button" tabIndex={-1} className={`${s.page} ${s.pageNext}`} aria-label="Scroll worlds right" onMouseDown={(e) => e.preventDefault()} onClick={() => page(1)}>▸</button>}
        </div>
      )}

      <footer className={s.foot}>
        <p className={s.keys} aria-hidden="true">
          <Kbd>←</Kbd><Kbd>→</Kbd> choose · <Kbd>Enter</Kbd> open · <Kbd>Esc</Kbd> menu · <Kbd>?</Kbd> shortcuts
        </p>
      </footer>
    </main>
  );
}

function WorldCard({ world: w, index }: { world: World; index: number }) {
  const chars = useCharacters(w.id).data;
  const now = useNow(60_000);
  const heads = (chars ?? []).filter((c) => c.status === "approved").slice(0, 5);
  const ref = useRef<HTMLButtonElement>(null);
  const open = (e: MouseEvent<HTMLButtonElement> | KeyboardEvent<HTMLButtonElement>) => {
    audio.playSfx("ui_shatter");
    const r = ref.current!.getBoundingClientRect();
    const origin = "clientX" in e && e.clientX ? { x: e.clientX, y: e.clientY } : { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    navigate({ name: "hub", worldId: w.id }, { transition: "shatter", sourceEl: ref.current!, origin });
  };
  const count = w.characterCount;
  return (
    <div role="listitem" className={s.slot} style={{ ["--i" as string]: index }}>
      <button
        ref={ref}
        type="button"
        data-card
        className={s.card}
        onClick={open}
        onMouseEnter={hoverTick}
        onFocus={hoverTick}
        aria-label={`${w.name}: ${count} character${count === 1 ? "" : "s"}, last active ${formatRelative(w.lastActiveAt, now)}`}
      >
        <span className={s.face}>
        <WorldCover cover={w.cover} className={s.cover} />
        <span className={s.shade} aria-hidden="true" />
        <span className={s.index} aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
        {w.isSeed && <Tape tone="paper" size="sm" className={s.seedTape}>DEMO WORLD</Tape>}
        <span className={s.info} aria-hidden="true">
          <span className={s.heads}>
            {heads.map((c, i) => (
              <img key={c.id} src={headUrl(c)} alt="" style={{ zIndex: 5 - i }} loading="lazy" />
            ))}
          </span>
          <span className={s.name}>{w.name}</span>
          <span className={s.meta}>
            <b>{count}</b> character{count === 1 ? "" : "s"}
            <span className={s.dot}>·</span>
            active {formatRelative(w.lastActiveAt, now)}
          </span>
        </span>
        </span>
        <span className={s.enter} aria-hidden="true">ENTER ▸</span>
      </button>
    </div>
  );
}
