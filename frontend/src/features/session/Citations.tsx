// D-59 / PRF-10 knowledge citations (C): inline `[n]` chips with a source popover, the pending chip while a reply
// streams, and the SOURCES strip under a cited bubble. Every entry opens O28 (Builder B's Source viewer).
// The popover is portalled (the log scrolls and clips) and wrapped in the speaker's palette.
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { Citation, KnowledgeSource } from "../../contract/types";
import { PaletteScope } from "../../theme/PaletteScope";
import { cx } from "../../ui/cx";
import { groupBySource, openCitation, typeGlyph } from "./citationUtils";
import { splitMarkers } from "./markdown";
import s from "./Citations.module.css";

export function TypeGlyph({ type, title, className }: { type: KnowledgeSource["type"]; title: string; className?: string }) {
  const g = typeGlyph(type, title);
  return <span className={cx(s.glyph, className)} data-type={type} aria-label={g === "LINK" ? "Web page" : g === "TEXT" ? "Text note" : `${g} file`}>{g}</span>;
}

// ── Chip + popover ───────────────────────────────────────────────────────────
const POP_W = 340;
const OPEN_MS = 90;
const CLOSE_MS = 180;

interface ChipProps {
  c: Citation;
  paletteId?: string | null;
  characterId?: string;
}

export function CiteChip({ c, paletteId, characterId }: ChipProps) {
  const ref = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const timer = useRef<number | undefined>(undefined);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ left: number; top: number; below: boolean } | null>(null);
  const id = useId();

  const schedule = useCallback((next: boolean) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(next), next ? OPEN_MS : CLOSE_MS);
  }, []);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const place = useCallback(() => {
    const el = ref.current;
    if (!el) return false;
    const r = el.getBoundingClientRect();
    if (r.bottom < 0 || r.top > window.innerHeight) return false;
    const h = popRef.current?.offsetHeight ?? 180;
    const below = r.top < h + 24;
    const left = Math.min(Math.max(12, r.left + r.width / 2 - 40), window.innerWidth - POP_W - 12);
    setPos({ left, top: below ? r.bottom + 10 : r.top - h - 10, below });
    return true;
  }, []);

  useLayoutEffect(() => {
    if (open) place();
  }, [open, place]);

  // The log scrolls under the anchor (focus scrolls it into view too): follow it; close once it leaves the screen.
  useEffect(() => {
    if (!open) return;
    const follow = () => {
      if (!place()) setOpen(false);
    };
    window.addEventListener("scroll", follow, true);
    window.addEventListener("resize", follow);
    return () => {
      window.removeEventListener("scroll", follow, true);
      window.removeEventListener("resize", follow);
    };
  }, [open, place]);

  const go = () => {
    window.clearTimeout(timer.current);
    setOpen(false);
    openCitation(c, characterId);
  };

  return (
    <>
      <button
        ref={ref}
        type="button"
        className={s.chip}
        aria-label={`Source ${c.n}: ${c.title}${c.locator ? `, ${c.locator}` : ""}. Open source`}
        aria-describedby={open ? id : undefined}
        data-cite={c.n}
        onClick={(e) => { e.stopPropagation(); go(); }}
        onMouseEnter={() => schedule(true)}
        onMouseLeave={() => schedule(false)}
        onFocus={() => { window.clearTimeout(timer.current); setOpen(true); }}
        onBlur={() => schedule(false)}
        onKeyDown={(e) => {
          if (e.key === "Escape" && open) {
            e.stopPropagation();
            setOpen(false);
          }
        }}
      >
        {c.n}
      </button>
      {open && createPortal(
        <PaletteScope paletteId={paletteId} className={s.popLayer}>
          <div
            ref={popRef}
            id={id}
            role="tooltip"
            className={cx(s.pop, pos?.below && s.popBelow)}
            style={{ left: pos?.left ?? -9999, top: pos?.top ?? -9999, width: POP_W } as CSSProperties}
            onMouseEnter={() => schedule(true)}
            onMouseLeave={() => schedule(false)}
          >
            <CitationCard c={c} />
            <button type="button" className={s.openBtn} onClick={go} tabIndex={-1}>
              Open source <span aria-hidden="true">▸</span>
            </button>
          </div>
        </PaletteScope>,
        document.body,
      )}
    </>
  );
}

/** Head (n · glyph · title · locator) + the quote: shared by the popover and Insight. */
export function CitationCard({ c, quote = true }: { c: Pick<Citation, "n" | "title" | "type" | "locator" | "quote">; quote?: boolean }) {
  return (
    <>
      <div className={s.popHead}>
        <span className={s.popN}>{c.n}</span>
        <TypeGlyph type={c.type} title={c.title} />
        <span className={s.popTitle}>{c.title}</span>
        {c.locator && <span className={s.popLoc}>{c.locator}</span>}
      </div>
      {quote && <blockquote className={s.quote}>{c.quote}</blockquote>}
    </>
  );
}

/** Quiet placeholder for a `[n]` while the reply is still streaming (it becomes a chip on turn.end). */
export function PendingChip({ n }: { n: number }) {
  return <span className={s.pending} aria-hidden="true">{n}</span>;
}

/** Text with `[n]` markers as pending chips (streaming). */
export function PendingText({ text }: { text: string }) {
  if (!text.includes("[")) return <>{text}</>;
  return <>{splitMarkers(text).map((x, i) => (typeof x === "number" ? <PendingChip key={i} n={x} /> : x))}</>;
}

/** Plain text with cited markers as chips (Backlog). `mark` decorates text runs (search highlight). */
export function CitedText({ text, cites, paletteId, characterId, mark = (t) => t }: {
  text: string; cites?: Citation[]; paletteId?: string | null; characterId?: string; mark?: (t: string) => ReactNode;
}) {
  if (!cites?.length) return <>{mark(text)}</>;
  const byN = new Map(cites.map((c) => [c.n, c]));
  return (
    <>
      {splitMarkers(text, new Set(byN.keys())).map((x, i) => (typeof x === "number"
        ? <CiteChip key={i} c={byN.get(x)!} paletteId={paletteId} characterId={characterId} />
        : <span key={i}>{mark(x)}</span>))}
    </>
  );
}

// ── SOURCES strip ────────────────────────────────────────────────────────────
export function SourcesStrip({ cites, characterId, compact, className }: { cites: Citation[]; characterId?: string; compact?: boolean; className?: string }) {
  const groups = groupBySource(cites);
  return (
    <div className={cx(s.strip, compact && s.stripCompact, className)} role="group" aria-label="Sources">
      <span className={s.stripLabel} aria-hidden="true">Sources</span>
      <ul className={s.stripList}>
        {groups.map((g) => {
          const locs = [...new Set(g.items.map((c) => c.locator).filter(Boolean))];
          return (
            <li key={g.sourceId}>
              <button
                type="button"
                className={s.entry}
                onClick={(e) => { e.stopPropagation(); openCitation(g.items[0], characterId); }}
                aria-label={`Open ${g.title}${locs.length ? `, ${locs.join(", ")}` : ""} (markers ${g.items.map((c) => c.n).join(", ")})`}
              >
                <span className={s.entryNs} aria-hidden="true">{g.items.map((c) => <span key={c.n} className={s.entryN}>{c.n}</span>)}</span>
                <TypeGlyph type={g.type} title={g.title} className={s.entryGlyph} />
                <span className={s.entryTitle}>{g.title}</span>
                {locs.length > 0 && <span className={s.entryLoc}>{locs.join(", ")}</span>}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
