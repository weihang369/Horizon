// One Knowledge tab card (PRF-08, design D20): readable sources open O28; indexing ones show the stage and a bar;
// failed ones offer ↻ Retry; keyword-only ones offer ↻ Index while a key is set (D-91), else say what a key adds.
// Every card can be deleted (after a confirm, by the caller). Presentational: the tab passes the actions. Owner: Builder B.
import type { CSSProperties } from "react";
import type { IngestProgress } from "@/client/HorizonClient";
import type { KnowledgeSource } from "@/contract/types";
import { typeGlyph } from "@/features/session/citationUtils";
import { Button, IconButton, Tape } from "@/ui";
import { CloseIcon } from "@/ui/icons";
import { cx } from "@/ui/cx";
import { formatAdded, isReadable, sourceFacts, STAGE_LABEL, STATUS_LABEL, STATUS_TONE, TYPE_NAME } from "./knowledge";
import k from "./knowledge.module.css";

export interface KnowledgeCardProps {
  d: KnowledgeSource;
  i: number;
  keySet: boolean;
  progress?: IngestProgress;
  onOpen: () => void;
  onDelete: () => void;
  onReindex: () => void;
}

export function KnowledgeCard({ d, i, keySet, progress, onOpen, onDelete, onReindex }: KnowledgeCardProps) {
  const facts = sourceFacts(d);
  const body = (
    <>
      <span className={cx(k.glyph, d.type === "url" && k.glyphLink)} aria-hidden="true">{typeGlyph(d.type, d.title)}</span>
      <span className={k.main}>
        <span className={k.kind}>{TYPE_NAME[d.type]}</span>
        <span className={k.title}>{d.title}</span>
        {d.url && <span className={k.url}>{d.url}</span>}
        <span className={k.facts}>{[...facts, d.addedAt ? `Added ${formatAdded(d.addedAt)}` : ""].filter(Boolean).join(" · ")}</span>
      </span>
      <span className={k.foot}>
        <Tape tone={STATUS_TONE[d.status]} size="sm">{STATUS_LABEL[d.status]}</Tape>
        {(d.citedCount ?? 0) > 0 && <span className={k.cited}>Cited {d.citedCount}×</span>}
        {isReadable(d) && <span className={k.open} aria-hidden="true">Read ▸</span>}
      </span>
    </>
  );
  const pct = Math.round((progress?.pct ?? 0) * 100);
  return (
    <li className={cx(k.card, k[`st_${d.status}`])} style={{ "--i": i } as CSSProperties}>
      {isReadable(d) ? (
        <button type="button" className={k.hit} onClick={onOpen} aria-label={`Open ${d.title}`}>{body}</button>
      ) : (
        <div className={k.hit}>
          {body}
          {d.status === "indexing" && <span className={k.scan} aria-hidden="true" />}
          {d.status === "indexing" && (
            <span className={k.stage} role="status">
              <span>{progress ? `${STAGE_LABEL[progress.stage]}…` : "Reading and indexing…"}</span>
              <span className={k.bar} role="progressbar" aria-label={`Indexing ${d.title}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
                <i style={{ width: `${pct}%` }} />
              </span>
            </span>
          )}
          {d.status === "failed" && (
            <span className={k.failRow}>
              <span className={k.err}>{d.error ?? "Couldn't read this source."}</span>
              <Button size="sm" variant="secondary" onClick={onReindex}>↻ Retry</Button>
            </span>
          )}
        </div>
      )}
      {d.status === "keyword_only" && (
        <div className={k.kwRow}>
          {keySet ? (
            <>
              <span>Found by keyword only. Index it to search by meaning too.</span>
              <Button size="sm" variant="secondary" onClick={onReindex}>↻ Index</Button>
            </>
          ) : (
            <span>Found by keyword only. A key enables search by meaning.</span>
          )}
        </div>
      )}
      {/* Deleting an indexing source is fine: the backend cancels the run first (knowledge-sources "Delete while indexing"). */}
      <IconButton label={`Delete ${d.title}`} size="sm" className={k.del} onClick={onDelete}>
        <CloseIcon width={14} height={14} />
      </IconButton>
    </li>
  );
}
