// S03 World Select (WLD-01): a centred rail of tilted world cards (−8°, 40 px overlap), "+ New World" always last.
// Hover/focus straightens to −4° and lifts 12 px with a hover tick; a card shatters into its Hub (README §3.1).
// Owner: Builder A.
import { useRef } from "react";
import type { KeyboardEvent, MouseEvent } from "react";
import { openOverlay } from "../../app/layers";
import { useShortcut } from "../../app/shortcuts";
import { audio } from "../../audio/engine";
import { useCharacters, useNow, useWorlds } from "../../client/hooks";
import type { World } from "../../contract/types";
import { formatRelative } from "../../domain/format";
import { navigate } from "../../router";
import { mockActions } from "../../stores/mock";
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

/** The seed debate replay World Select links to directly (doc 06). */
const FEATURED = { worldId: "wld_seedMeridian", sessionId: "ses_seedDebate4Day" } as const;

export function WorldSelectScreen() {
  useHouseScreen();
  const { data: worlds, loading, error, reload } = useWorlds();
  const rail = useRef<HTMLDivElement>(null);
  const sorted = worlds ? [...worlds].sort((a, b) => Date.parse(b.lastActiveAt) - Date.parse(a.lastActiveAt)) : [];

  // ←/→ (and Home/End) choose a card from anywhere on the screen, not only once a card has focus: after a load or a
  // mouse click focus sits on <body>, and the footer promises the keys work.
  const moveFocus = (key: "arrowright" | "arrowleft" | "home" | "end") => {
    const items = [...(rail.current?.querySelectorAll<HTMLElement>("[data-card]") ?? [])];
    if (!items.length) return;
    const i = items.indexOf(document.activeElement as HTMLElement);
    const next = key === "home" ? 0 : key === "end" ? items.length - 1 : i < 0 ? 0 : i + (key === "arrowright" ? 1 : -1);
    const el = items[Math.max(0, Math.min(items.length - 1, next))];
    el.focus();
    el.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
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
          <Button variant="ghost" size="sm" onClick={() => void mockActions.resetDemoData()}>Restore demo data</Button>
        </div>
      ) : !error && (
        <div ref={rail} className={s.rail} role="list" aria-label="Worlds">
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
