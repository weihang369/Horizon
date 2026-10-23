// O28 Source viewer (D-59, PRF-08 AC2, PRF-10): a knowledge source read like a document pinned to the corkboard.
// Every passage in order with its locator in the margin; the cited `chunkId` is scrolled to and marker-swept. Opened
// from the SOURCES strip it marks every marker of the reply in this source, with a row to jump between them (U-37).
// Removed source + `cited` snapshot → "removed after the answer" state (PRF-10 AC5). Esc/trap/restore come from
// the modal layer.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import type { OverlayComponentProps } from "@/app/overlayTypes";
import { client } from "@/client";
import { useCharacter } from "@/client/hooks";
import type { Character, KnowledgeChunk, KnowledgeSource } from "@/contract/types";
import { useMotionPrefs } from "@/motion";
import { paletteClass } from "@/theme";
import { Button, CloseIcon, IconButton, Skeleton, Tape } from "@/ui";
import { cx } from "@/ui/cx";
import { typeGlyph } from "@/features/session/citationUtils";
import { plainText, renderMarkdown } from "@/features/session/markdown";
import { formatAdded, sourceFacts, STATUS_LABEL, STATUS_TONE, TYPE_NAME } from "./knowledge";
import s from "./SourceViewer.module.css";

type Load =
  | { state: "loading" }
  | { state: "ready"; source: KnowledgeSource; chunks: KnowledgeChunk[] }
  | { state: "error"; message: string };

function useSource(sourceId: string): Load {
  // Keyed by id so a new sourceId reads as loading without a synchronous reset in the effect.
  const [got, setGot] = useState<{ id: string; load: Load } | null>(null);
  useEffect(() => {
    let live = true;
    client.characters.knowledgeSource(sourceId).then(
      (r) => live && setGot({ id: sourceId, load: { state: "ready", source: r.source, chunks: r.chunks } }),
      (err: unknown) => live && setGot({ id: sourceId, load: { state: "error", message: err instanceof Error ? err.message : "Source not found." } }),
    );
    return () => void (live = false);
  }, [sourceId]);
  return got?.id === sourceId ? got.load : { state: "loading" };
}

function OwnerChip({ c }: { c: Character }) {
  const face = c.emotions.neutral?.url;
  return (
    <span className={s.owner}>
      <span className={s.ownerFace} aria-hidden="true">{face ? <img src={face} alt="" draggable={false} /> : c.profile.name[0]}</span>
      <span className={s.ownerName}>{c.profile.name}</span>
    </span>
  );
}

interface Mark { n: number; chunkId: string; locator?: string; quote: string }

export function SourceViewer({ close, sourceId, chunkId, characterId, cited, also }: OverlayComponentProps<"O28">) {
  const load = useSource(sourceId);
  const source = load.state === "ready" ? load.source : null;
  const owner = useCharacter(characterId ?? source?.characterId).data ?? null;
  const reduced = useMotionPrefs().reduced;
  const bodyRef = useRef<HTMLDivElement>(null);
  const targetRef = useRef<HTMLElement>(null);
  const [swept, setSwept] = useState(0);
  const [at, setAt] = useState(0);

  const chunks = load.state === "ready" ? load.chunks : [];
  // Every marker this viewer is for, in marker order: the chip's one, or the strip's whole group. n = 0: retrieved only.
  const marks: Mark[] = [...(chunkId ? [{ n: cited?.n ?? 0, chunkId, locator: cited?.locator, quote: cited?.quote ?? "" }] : []), ...(also ?? [])]
    .sort((a, b) => a.n - b.n);
  const inDoc = (m: Mark) => chunks.some((x) => x.id === m.chunkId);
  const found = marks.filter(inDoc);
  const missing = load.state === "ready" ? marks.filter((m) => m.n && !inDoc(m)) : [];
  const active = found[Math.min(at, found.length - 1)];
  const hit = active ? chunks.find((x) => x.id === active.chunkId) : undefined;
  const marksOn = (id: string) => found.filter((m) => m.chunkId === id).map((m) => m.n);

  // Land on the cited passage (instant: the marker sweep is the attention cue), or at the top.
  useLayoutEffect(() => {
    if (load.state !== "ready") return;
    const el = targetRef.current;
    const body = bodyRef.current;
    if (!el || !body) return;
    const top = el.offsetTop - body.clientHeight / 2 + el.offsetHeight / 2;
    body.scrollTo({ top: Math.max(0, top), behavior: "auto" });
  }, [load.state, hit?.id]);

  // The lazy overlay mounts after the layer's trap ran: land focus inside once content exists (the document
  // region for reading with the keyboard, or Close on the error card). Focus restore stays with the layer.
  const dialogRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const d = dialogRef.current;
    if (!d || load.state === "loading" || d.contains(document.activeElement)) return;
    (load.state === "ready" ? bodyRef.current : d.querySelector<HTMLElement>("button"))?.focus({ preventScroll: true });
  }, [load.state]);

  // A jump (the footer button, or a marker in the jump row) scrolls to the active passage once it has rendered.
  useEffect(() => {
    const el = targetRef.current;
    const body = bodyRef.current;
    if (!swept || !el || !body) return;
    body.scrollTo({ top: Math.max(0, el.offsetTop - body.clientHeight / 2 + el.offsetHeight / 2), behavior: reduced ? "auto" : "smooth" });
  }, [swept, reduced]);
  const jump = (i = at) => {
    setAt(i);
    setSwept((n) => n + 1);
  };

  const pal = paletteClass(owner?.paletteId);
  const closeBtn = <IconButton label="Close source viewer" onClick={close} className={s.close}><CloseIcon width={18} height={18} /></IconButton>;

  // ── Removed / not found ───────────────────────────────────────────────────
  if (load.state === "error") {
    return (
      <div ref={dialogRef} className={cx(pal, s.viewer, s.viewerSmall)} role="dialog" aria-modal="true" aria-label={cited ? `Removed source: ${cited.title}` : "Source unavailable"}>
        <header className={s.head}>
          <span className={cx(s.glyph, s.glyphGone)} aria-hidden="true">{cited ? "GONE" : "?"}</span>
          <div className={s.headMain}>
            <p className={s.kicker}>O28 · Source viewer</p>
            <h2 className={s.title}>{cited?.title ?? "Source unavailable"}</h2>
            <div className={s.metaRow}>
              {owner && <OwnerChip c={owner} />}
              <Tape tone="error" size="sm">{cited ? "Removed" : "Not found"}</Tape>
            </div>
          </div>
          {closeBtn}
        </header>
        {cited ? (
          <div className={s.removed}>
            <p className={s.removedLead}>
              <b>This source was removed after the answer.</b> Here {marks.length > 1 ? "are the passages" : "is the passage"} {owner ? owner.profile.name.split(" ")[0] : "the character"} quoted at the time, kept with the reply.
            </p>
            {marks.map((m) => (
              <figure key={m.n} className={s.snapshot}>
                <span className={s.pin} aria-hidden="true" />
                <figcaption className={s.snapCap}>
                  <span className={s.cn}>[{m.n}]</span>
                  <span className={s.snapTitle}>{cited.title}</span>
                  {m.locator && <span className={s.snapLoc}>{m.locator}</span>}
                </figcaption>
                <blockquote className={cx(s.snapQuote, s.text)}>{renderMarkdown(m.quote)}</blockquote>
                <span className={s.stamp} aria-hidden="true">Removed</span>
              </figure>
            ))}
          </div>
        ) : (
          <div className={s.removed}>
            <p className={s.removedLead}><b>We couldn't open this source.</b> It may have been deleted. {load.message}</p>
          </div>
        )}
        <footer className={s.foot}><span className={s.hint}>Esc to close</span><Button variant="secondary" size="sm" onClick={close}>Close</Button></footer>
      </div>
    );
  }

  // ── Loading / document ────────────────────────────────────────────────────
  const facts = source ? sourceFacts(source) : [];
  const cites = source?.citedCount ?? 0;
  const glyph = source ? typeGlyph(source.type, source.title) : "…";
  const label = source ? `${TYPE_NAME[source.type]}: ${source.title}` : "Loading source";

  return (
    <div ref={dialogRef} className={cx(pal, s.viewer)} role="dialog" aria-modal="true" aria-label={label} aria-busy={load.state === "loading"}>
      <header className={s.head}>
        <span className={cx(s.glyph, source?.type === "url" && s.glyphLink)} aria-hidden="true">{glyph}</span>
        <div className={s.headMain}>
          <p className={s.kicker}>{source ? TYPE_NAME[source.type] : "Source"} · O28 Source viewer</p>
          {source ? <h2 className={s.title}>{source.title}</h2> : <Skeleton lines={1} height={30} />}
          {source && (
            <div className={s.metaRow}>
              {owner && <OwnerChip c={owner} />}
              <Tape tone={STATUS_TONE[source.status]} size="sm">{STATUS_LABEL[source.status]}</Tape>
              {facts.length > 0 && <span className={s.facts}>{facts.join(" · ")}</span>}
              {cites > 0 && <span className={s.cited}>Cited {cites}×</span>}
              {source.addedAt && <span className={s.facts}>Added {formatAdded(source.addedAt)}</span>}
            </div>
          )}
          {source?.url && <p className={s.url} title="Shown as text: the preview never fetches pages">{source.url}</p>}
          {missing.map((m) => (
            <p key={m.n} className={s.notice} role="note">
              <b>[{m.n}] {m.locator ?? "Cited passage"}</b> isn't in this source any more (it was re-indexed). Quoted at the time: “{plainText(m.quote)}”
            </p>
          ))}
          {found.length > 1 && (
            <div className={s.marks} role="group" aria-label="Cited passages">
              <span className={s.marksLabel} aria-hidden="true">Cited here</span>
              {found.map((m, i) => (
                <button key={m.n} type="button" className={s.markBtn} aria-pressed={m === active} onClick={() => jump(i)}
                  aria-label={`Jump to [${m.n}]${m.locator ? `, ${m.locator}` : ""}`}>{m.n}</button>
              ))}
            </div>
          )}
        </div>
        {closeBtn}
      </header>

      <div className={s.desk}>
        <div ref={bodyRef} className={s.scroll} tabIndex={0} aria-label="Passages">
          <article className={s.sheet}>
            <span className={cx(s.tapeCorner, s.tapeL)} aria-hidden="true" />
            <span className={cx(s.tapeCorner, s.tapeR)} aria-hidden="true" />
            {load.state === "loading" && <Skeleton lines={8} height={18} />}
            {load.state === "ready" && chunks.length === 0 && (
              <p className={s.emptyDoc}>{source?.status === "failed" ? source.error ?? "This source failed to index." : source?.status === "indexing" ? "Still reading this source. Passages appear once indexing finishes." : "No passages indexed yet."}</p>
            )}
            {chunks.map((x, i) => {
              const ns = marksOn(x.id);
              const isHit = ns.length > 0;
              const isActive = x.id === hit?.id;
              return (
                <section
                  key={x.id}
                  ref={isActive ? (el) => { targetRef.current = el; } : undefined}
                  className={cx(s.passage, isHit && s.hit)}
                  style={{ "--i": Math.min(i, 12) } as CSSProperties}
                  aria-current={isActive ? "true" : undefined}
                  aria-label={`${x.locator ?? `Passage ${i + 1}`}${isHit ? ", cited passage" : ""}`}
                >
                  <div className={s.margin}>
                    <span className={s.loc}>{x.locator ?? `#${i + 1}`}</span>
                    {isHit && <span className={s.hitTag}>{cited ? `${ns.map((n) => `[${n}]`).join("")} cited` : "Retrieved"}</span>}
                  </div>
                  <div key={isActive ? swept : undefined} className={cx(s.text, isHit && s.marker)}>{renderMarkdown(x.text)}</div>
                </section>
              );
            })}
            {chunks.length > 0 && <p className={s.end}>End of indexed passages · {chunks.length} of {source?.chunks ?? chunks.length}</p>}
          </article>
        </div>
      </div>

      <footer className={s.foot}>
        <span className={s.hint}>
          {hit ? <>Highlighted: {found.length > 1 ? `the passages behind ${found.map((m) => `[${m.n}]`).join(" ")}` : `the passage ${cited ? `behind [${active.n}]` : "the character retrieved"}`}.</> : "Passages as indexed, in order."}
          {source?.type === "url" && " The preview never fetches the page."}
        </span>
        <span className={s.footActions}>
          {hit && <Button variant="ghost" size="sm" onClick={() => jump()}>▸ Jump to {found.length > 1 ? `[${active.n}]` : hit.locator ?? "passage"}</Button>}
          <Button variant="secondary" size="sm" onClick={close}>Close</Button>
        </span>
      </footer>
    </div>
  );
}
