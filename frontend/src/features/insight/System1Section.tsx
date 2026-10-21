// The "System 1 · Jev" section of O08 (docs/ai/13 W1; system1-trace "The Insight section"): every Jev question behind
// the turn, grouped by purpose and headed by that purpose's latency (or "fallback"). Each row (U-29 meter rows) reads:
// the label and what code did, then the answer with a bar of the value code tested and a tick at its line, `p` or
// confidence with its band (INS-01 AC4), and each comparison as "value ≥ threshold".
// `not_used` rows (asked about the other candidates) fold away. IDs resolve to names or titles; text never appears.
import { Fragment, useState } from "react";
import type { CSSProperties } from "react";
import type { System1Row, TurnTrace } from "../../contract/types";
import { probBand } from "../../domain/format";
import { cx } from "../../ui/cx";
import s from "./InsightDrawer.module.css";

// U-35: one panel name for the plan in every mode, with a tag for when it was made; a line under each panel says
// what it is; plain labels for the rows whose bank label is shorthand (the question Jev gets is unchanged).
const PLAN_TAG: Record<string, string> = {
  turn_plan: "before the reply",
  follow_plan: "second reply",
  debate_plan: "made ahead",
  route: "who replies",
};
const PURPOSE_LABEL: Record<string, string> = {
  ...Object.fromEntries(Object.keys(PLAN_TAG).map((k) => [k, "plan"])),
  deep_check: "passages",
  "deep_check:recall": "earlier lines",   // M13 (memory D35): recall's Jev call 2, apart from the passages
  guardrail: "output check",
  face_check: "after the reply",
};
const PURPOSE_WHY: Record<string, string> = {
  ...Object.fromEntries(Object.keys(PLAN_TAG).map((k) => [k, "Jev's checks before writing: every question in one request; code reads each answer against its line."])),
  deep_check: "Each passage the search found, judged by Jev; code keeps the best usable ones.",
  "deep_check:recall": "Each earlier line or memory the search found, judged by Jev; up to 3 are kept.",
  guardrail: "The finished reply, checked against the rules before it's shown.",
  face_check: "Do the face and the words agree? Shown here only: the face isn't changed.",
};
const ROW_LABEL: Record<string, string> = {
  english: "message in English?",
  standalone: "clear without the earlier lines?",
  at_risk: "user may be at risk?",
  unsafe_note: "your note asks for something unsafe?",
  talk_finished: "has the scene run its course?",
};

export interface System1Group {
  purpose: string;
  label: string;
  tag?: string;
  why?: string;
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
      purpose, label: PURPOSE_LABEL[purpose] ?? purpose.replace(/_/g, " "), tag: PLAN_TAG[purpose], why: PURPOSE_WHY[purpose],
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

/** The row's tone: did the value cross the line its meter draws (the first comparison)? A row with no comparison was
 * used as answered. Later comparisons are further reads of the same answer (a kept passage that isn't "found" is not
 * greyed). */
function toneOf(r: System1Row): "pass" | "miss" | "fallback" | "unused" {
  if (r.result === "fallback") return "fallback";
  if (r.result === "not_used") return "unused";
  if (r.result === "below_threshold") return "miss";
  const line = r.compared?.[0];
  return line && line.value < line.threshold ? "miss" : "pass";
}

// U-36: a passage row compares two numbers from one answer; each says which.
const CMP_LABEL: Record<string, string> = { "passage:t_keep": "usable", "passage:t_found": "answers" };

const cmpLine = (r: System1Row) => (r.compared ?? []).map((c) => {
  const label = CMP_LABEL[`${r.id}:${c.name}`];
  return `${label ? `${label} ` : ""}${r2(c.value).toFixed(2)} ${c.value >= c.threshold ? "≥" : "<"} ${r2(c.threshold).toFixed(2)}`;
}).join(" · ");

export type PassageOutcome = "found" | "found_together" | "partly" | "not_found" | "fallback";

const passages = (n: number) => (n === 1 ? "1 passage" : `${n} passages`);

/** U-36: the passages' outcome, read back from the rows as the keep rule decides it (backend ai/agent/keep.py):
 * found (a passage's p_answers ≥ t_found, or the set check said yes) → else fallback (a check missing) → partly (some
 * usable) → not found. Turns saved before the rows carried t_found read it from the set check (asked only when none
 * was found) or from two usable passages without one; a single usable passage without it gets no line. */
export function passageResult(rows: System1Row[]): { outcome: PassageOutcome; label: string; text: string } | null {
  const ps = rows.filter((r) => r.id === "passage");
  if (!ps.length) return null;
  const crossed = (r: System1Row, name: string) => r.compared?.some((c) => c.name === name && c.value >= c.threshold) ?? false;
  const kept = ps.filter((r) => r.action === "kept" || r.action === "kept by search order").length;
  const usable = ps.filter((r) => crossed(r, "t_keep")).length;
  const set = rows.find((r) => r.id === "passage_set");
  const missing = ps.some((r) => r.result === "fallback");
  const saved = ps.some((r) => r.compared?.some((c) => c.name === "t_found"));
  if (ps.some((r) => crossed(r, "t_found")) || (!saved && !set && !missing && usable >= 2))
    return { outcome: "found", label: "found", text: `A passage answers it; the reply gets the best ${passages(kept)}.` };
  if (set?.answer === "yes")
    return { outcome: "found_together", label: "found together", text: `No single passage answers it, but these do together; the reply gets ${passages(kept)}.` };
  if (missing)
    return { outcome: "fallback", label: "fallback", text: `Not every check came back; the reply gets the top ${passages(kept)} in search order, unscored.` };
  if (!saved && !set && usable) return null;   // the set check is only asked when none was found
  if (usable)
    return { outcome: "partly", label: "partly", text: `No passage fully answers it; the reply gets the ${kept === 1 ? "1 usable passage" : `${kept} usable passages`}.` };
  return { outcome: "not_found", label: "not found", text: "No passage is usable; the reply gets none." };
}

/** Meter rows (U-29): label and verdict, then the answer with a bar of the value code tested and a tick at its line. */
function Row({ r, trace, nameOf }: { r: System1Row; trace?: TurnTrace; nameOf: (id: string) => string }) {
  const value = r.p ?? r.confidence;
  const band = value !== undefined ? probBand(r2(value)) : null;
  const line = r.compared?.[0];
  const bar = line?.value ?? value;
  const tone = toneOf(r);
  const verdict = r.action ?? (r.result === "shown_only" ? "for Insight only" : r.result === "fallback" ? "fallback" : null);
  return (
    <li className={s.s1Row} data-result={r.result} data-tone={tone}>
      <div className={s.s1Top}>
        <span className={s.s1Label}>{ROW_LABEL[r.id] ?? r.label}{r.about ? <span className={s.s1About}> · {resolveId(r.about, trace, nameOf)}</span> : null}</span>
        {verdict && <span className={s.s1Verdict}>{verdict}</span>}
      </div>
      <div className={s.s1Meter}>
        <b className={s.s1Answer}>{/^[a-z]{2,6}_/.test(r.answer) ? resolveId(r.answer, trace, nameOf) : r.answer}</b>
        {bar !== undefined ? (
          <span className={s.s1Gauge} aria-hidden="true">
            <span className={s.s1Track}><span className={s.s1Fill} style={{ "--p": Math.max(0, Math.min(1, bar)) } as CSSProperties} /></span>
            {line && <span className={s.s1Tick} style={{ left: `${Math.max(0, Math.min(1, line.threshold)) * 100}%` }} />}
          </span>
        ) : <span className={s.s1Gauge} />}
        {value !== undefined && (
          <span className={s.s1Prob}>
            {r.p !== undefined ? "p" : "conf"} {r2(value).toFixed(2)}
            <span className={cx(s.band, band && s[`band_${band}`])}> {band}</span>
          </span>
        )}
      </div>
      {r.compared?.length ? <p className={s.s1Cmp}>{cmpLine(r)}</p> : null}
    </li>
  );
}

/** U-34: "needs documents?" said search, but no passage was checked because the search matched nothing. The section
 * said so by saying nothing; this is the line it shows after the group that decided to search. */
function searchedNothing(trace: TurnTrace | undefined, groups: System1Group[]): { after: string; about?: string } | null {
  if (groups.some((g) => g.purpose === "deep_check") || !trace?.knowledge || trace.knowledge.retrieved.length) return null;
  const g = groups.find((x) => x.rows.some((r) => r.id === "docs" && r.answer === "yes"));
  const row = g?.rows.find((r) => r.id === "docs" && r.answer === "yes");
  return g ? { after: g.purpose, about: row?.about } : null;
}

export function System1Rows({ trace, nameOf }: { trace?: TurnTrace; nameOf: (id: string) => string }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const groups = groupSystem1(trace);
  const nothing = searchedNothing(trace, groups);
  return (
    <div className={s.s1}>
      {groups.map((g) => {
        const result = g.purpose === "deep_check" ? passageResult(g.rows) : null;
        return (
          <Fragment key={g.purpose}>
            <div className={s.s1Group} data-purpose={g.purpose}>
              <p className={s.s1Head}>
                {g.label}
                {g.tag && <span className={s.s1Tag}>{g.tag}</span>}
                <span className={s.s1Lat} data-fallback={g.fallback || undefined}>{g.fallback ? "fallback" : g.latencyMs !== null ? `${Math.round(g.latencyMs)} ms` : "—"}</span>
              </p>
              {g.why && <p className={s.s1Why}>{g.why}</p>}
              {result && <p className={s.s1Result} data-outcome={result.outcome}><b>{result.label}</b>{result.text}</p>}
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
            {nothing?.after === g.purpose && (
              <div className={s.s1Group} data-purpose="deep_check" data-empty="">
                <p className={s.s1Head}>passages<span className={s.s1Lat}>—</span></p>
                <p className={s.s1Why}>{PURPOSE_WHY.deep_check}</p>
                <p className={s.s1Empty}>
                  The search matched nothing in {nothing.about ? `${resolveId(nothing.about, trace, nameOf)}'s` : "the"} documents, so no
                  passage was checked and the reply used none.
                </p>
              </div>
            )}
          </Fragment>
        );
      })}
    </div>
  );
}
