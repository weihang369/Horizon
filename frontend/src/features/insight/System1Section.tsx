// The "System 1 · Jev" section of O08 (docs/ai/13 W1; system1-trace "The Insight section"): every Jev question behind
// the turn, grouped by purpose and headed by that purpose's latency (or "fallback"). Each row reads: the label and
// answer, `p` or confidence with its band (INS-01 AC4), each comparison as "value ≥ threshold", and what code did.
// `not_used` rows (asked about the other candidates) fold away. IDs resolve to names or titles; text never appears.
import { useState } from "react";
import type { System1Row, TurnTrace } from "../../contract/types";
import { probBand } from "../../domain/format";
import { cx } from "../../ui/cx";
import s from "./InsightDrawer.module.css";

const PURPOSE_LABEL: Record<string, string> = {
  turn_plan: "before the reply",
  follow_plan: "after the first reply",
  debate_plan: "debate plan",
  deep_check: "passages",
  "deep_check:recall": "earlier lines",   // M13 (memory D35): recall's Jev call 2, apart from the passages
  guardrail: "output check",
  face_check: "after the reply",
  route: "who replies",
};

export interface System1Group {
  purpose: string;
  label: string;
  latencyMs: number | null;
  fallback: boolean;
  rows: System1Row[];
  folded: System1Row[];
}

const r2 = (p: number) => Math.round(p * 100) / 100;
const SHORT = 40;
const short = (t: string) => (t.length <= SHORT ? t : `${t.slice(0, SHORT - 1).trimEnd()}…`);

/** INS-01 AC3 / AC5: hidden with no rows, and left out of Compact (presenter) mode. */
export const showSystem1 = (trace: TurnTrace | undefined, compact: boolean): boolean =>
  !compact && !!trace?.system1?.questions.length;

/** M13 (memory D35): recall's rows share `deep_check` with the passages but are their own group, "earlier lines". */
const groupOf = (r: System1Row): string => (r.purpose === "deep_check" && r.id === "recall" ? "deep_check:recall" : r.purpose);

/** Rows grouped by purpose in first-seen order; the header latency is the slowest of that purpose's calls. */
export function groupSystem1(trace: TurnTrace | undefined): System1Group[] {
  const rows = trace?.system1?.questions ?? [];
  const order: string[] = [];
  const by = new Map<string, System1Row[]>();
  for (const r of rows) {
    const g = groupOf(r);
    if (!by.has(g)) { by.set(g, []); order.push(g); }
    by.get(g)!.push(r);
  }
  return order.map((purpose) => {
    const all = by.get(purpose)!;
    const callPurpose = purpose.split(":")[0];
    const lat = (trace?.calls ?? []).filter((c) => c.purpose === callPurpose).map((c) => c.latencyMs);
    const shown = all.filter((r) => r.result !== "not_used");
    return {
      purpose, label: PURPOSE_LABEL[purpose] ?? purpose.replace(/_/g, " "),
      latencyMs: lat.length ? Math.max(...lat) : null,
      fallback: all.length > 0 && all.every((r) => r.result === "fallback"),
      rows: shown, folded: all.filter((r) => r.result === "not_used"),
    };
  });
}

/** An ID in `about` or `answer` → a readable name: characters by first name, pieces by title, never stored text. */
export function resolveId(id: string, trace: TurnTrace | undefined, nameOf: (id: string) => string): string {
  if (id.startsWith("chr_")) return nameOf(id);
  if (id.startsWith("kch_")) {
    const k = trace?.knowledge?.retrieved.find((x) => x.chunkId === id);
    return k ? `${k.title}${k.locator ? ` (${k.locator})` : ""}` : "a passage";
  }
  // M13 (memory D35): recall's ids, through what the turn was given (as `kch_` resolves through `retrieved`)
  if (id.startsWith("mem_")) {
    const m = trace?.memory?.recalled.find((x) => x.memoryItemId === id);
    return m ? `“${short(m.text)}”` : "a memory";
  }
  if (id.startsWith("msg_")) {
    const l = trace?.contextInSession?.find((x) => x.messageId === id);
    return l ? `“${short(l.text)}”` : "a message";
  }
  return id;
}

function Row({ r, trace, nameOf }: { r: System1Row; trace?: TurnTrace; nameOf: (id: string) => string }) {
  const value = r.p ?? r.confidence;
  const band = value !== undefined ? probBand(r2(value)) : null;
  return (
    <li className={s.s1Row} data-result={r.result}>
      <span className={s.s1Label}>{r.label}{r.about ? <span className={s.s1About}> · {resolveId(r.about, trace, nameOf)}</span> : null}</span>
      <span className={s.s1Answer}>
        <b>{/^[a-z]{2,6}_/.test(r.answer) ? resolveId(r.answer, trace, nameOf) : r.answer}</b>
        {value !== undefined && (
          <span className={s.s1Prob}>
            {r.p !== undefined ? "p" : "conf"} {r2(value).toFixed(2)}
            <span className={cx(s.band, band && s[`band_${band}`])}> · {band}</span>
          </span>
        )}
      </span>
      {r.compared?.map((c) => (
        <span key={c.name} className={s.s1Cmp}>
          {r2(c.value).toFixed(2)} {c.value >= c.threshold ? "≥" : "<"} {r2(c.threshold).toFixed(2)}
        </span>
      ))}
      {r.action && <span className={s.s1Action}>→ {r.action}</span>}
      {r.result === "shown_only" && <span className={s.s1Action}>(shown only)</span>}
    </li>
  );
}

export function System1Rows({ trace, nameOf }: { trace?: TurnTrace; nameOf: (id: string) => string }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const groups = groupSystem1(trace);
  return (
    <div className={s.s1}>
      {groups.map((g) => (
        <div key={g.purpose} className={s.s1Group} data-purpose={g.purpose}>
          <p className={s.s1Head}>
            {g.label}
            <span> · {g.fallback ? "fallback" : g.latencyMs !== null ? `${Math.round(g.latencyMs)} ms` : "—"}</span>
          </p>
          <ul className={s.s1List}>
            {g.rows.map((r, i) => <Row key={`${r.id}:${r.about ?? ""}:${i}`} r={r} trace={trace} nameOf={nameOf} />)}
          </ul>
          {g.folded.length > 0 && (
            <>
              <button type="button" className={s.s1Fold} aria-expanded={!!open[g.purpose]}
                onClick={() => setOpen((o) => ({ ...o, [g.purpose]: !o[g.purpose] }))}>
                asked about the others ({g.folded.length})
              </button>
              {open[g.purpose] && (
                <ul className={cx(s.s1List, s.s1Folded)}>
                  {g.folded.map((r, i) => <Row key={`f:${r.id}:${r.about ?? ""}:${i}`} r={r} trace={trace} nameOf={nameOf} />)}
                </ul>
              )}
            </>
          )}
        </div>
      ))}
    </div>
  );
}
