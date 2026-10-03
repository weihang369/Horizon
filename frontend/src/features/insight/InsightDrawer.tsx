// O08 Insight drawer (INS-01, doc 04 §8): "see the AI think". A 400 px ink panel (300 compact in Presenter Mode)
// that reads the selected character message's TurnTrace: Routing → Emotion → Model → Energy → Memory → In-session
// recall → Context → Guardrail. Sections without data are not rendered. It pushes the log in S07 (the frame reserves
// the space) and overlays the right column in S09/S10/S12. ↑↓ in the log, ‹ › here, or a click selects a message.
import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { useStore } from "zustand";
import { client } from "../../client";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { selectInsight } from "../../app/layers";
import { useShortcut } from "../../app/shortcuts";
import { PortraitCard } from "../../character/PortraitCard";
import { emotionMeta } from "../../character/emotionMeta";
import type { Character, Citation, Message, TurnTrace } from "../../contract/types";
import { formatUsd, probBand } from "../../domain/format";
import { useMotionPrefs } from "../../motion/prefs";
import { entities } from "../../stores/entities";
import { usePrefs } from "../../stores/prefs";
import { useUi } from "../../stores/ui";
import { PaletteScope } from "../../theme/PaletteScope";
import { IconButton } from "../../ui/Button";
import { ProbBar, StackedBar } from "../../ui/Data";
import { Drawer } from "../../ui/Panels";
import { Tape } from "../../ui/Tape";
import { cx } from "../../ui/cx";
import { useKnowledge, useStreamText } from "../../client/hooks";
import { useSlotRuntime } from "../session/slot";
import { plainText } from "../session/markdown";
import { TypeGlyph } from "../session/Citations";
import { openCitation } from "../session/citationUtils";

/** Bars and bands use the same 2-decimal value, so "0.70" never reads "MED" (no false precision, INS-01 AC4). */
const r2 = (p: number) => Math.round(p * 100) / 100;
import s from "./InsightDrawer.module.css";

const firstName = (n?: string) => (n ? n.split(" ").find((w) => !/^(dr|prof|mr|ms|mrs)\.?$/i.test(w)) ?? n : "");
const isChar = (m?: Message): m is Message => !!m && m.author.type === "character" && !!m.author.characterId;

const traceCache = new Map<string, Promise<TurnTrace | null>>();

/** Values arm one frame after a selection change, so bars fill from zero ("watch it think"). */
function useArmed(key: string | undefined): boolean {
  const [armed, setArmed] = useState<string | undefined>(undefined);
  useEffect(() => {
    const r = requestAnimationFrame(() => requestAnimationFrame(() => setArmed(key)));
    return () => cancelAnimationFrame(r);
  }, [key]);
  return armed === key;
}

const CONTEXT_COLORS: Record<string, string> = {
  system: "var(--paper-300)",
  persona: "var(--horizon-500)",
  memory: "var(--horizon-300)",
  knowledge: "var(--signal-ok)",
  history: "var(--c-primary)",
  user: "var(--signal-warn)",
  mode: "var(--blush)",
};

const FORCED_LABEL: Record<NonNullable<NonNullable<TurnTrace["routing"]>["forcedBy"]>, string> = {
  user_ask: "Forced by you · Ask",
  mention: "Forced by you · @mention",
  nudge: "Forced by you · Speak next",
  round_order: "Round order",
};

function Section({ n, title, aside, children, i }: { n: string; title: string; aside?: ReactNode; children: ReactNode; i: number }) {
  return (
    <section className={s.section} style={{ "--i": i } as CSSProperties} aria-label={title}>
      <header className={s.secHead}>
        <span className={s.secNum} aria-hidden="true">{n}</span>
        <h3 className={s.secTitle}>{title}</h3>
        {aside && <span className={s.secAside}>{aside}</span>}
      </header>
      {children}
    </section>
  );
}

function Pipeline({ trace, streaming }: { trace?: TurnTrace; streaming: boolean }) {
  const steps = trace?.graph?.path?.length
    ? trace.graph.path.map((p) => ({ k: p, on: true }))
    : [
      { k: "Route", on: !!trace?.routing },
      { k: "Recall", on: !!(trace?.memory || trace?.knowledge || trace?.contextInSession || trace?.context) },
      { k: "Generate", on: !!trace?.model },
      { k: "Emotion", on: !!trace?.emotion },
      { k: "Guard", on: !!trace?.guardrail },
    ];
  return (
    <ol className={cx(s.pipe, streaming && s.pipeLive)} aria-label="Turn pipeline">
      {steps.map((st, i) => (
        <li key={st.k} className={cx(s.node, (st.on || streaming) && s.nodeOn)} style={{ "--i": i } as CSSProperties}>
          <span>{st.k}</span>
        </li>
      ))}
    </ol>
  );
}

function LatencyBar({ first, total, armed }: { first: number; total: number; armed: boolean }) {
  const f = total > 0 ? Math.min(1, first / total) : 0;
  return (
    <div className={s.latency}>
      <div className={s.latTrack} aria-hidden="true">
        <span className={s.latWait} style={{ transform: `scaleX(${armed ? f : 0})` }} />
        <span className={s.latStream} style={{ left: `${f * 100}%`, transform: `scaleX(${armed ? 1 : 0})` }} />
        <span className={s.latTick} style={{ left: `${f * 100}%` }} />
      </div>
      <div className={s.latLegend}>
        <span><b>{(first / 1000).toFixed(2)} s</b> first token</span>
        <span><b>{(total / 1000).toFixed(2)} s</b> total</span>
      </div>
    </div>
  );
}

function TokenSplit({ tin, cached, tout }: { tin: number; cached: number; tout: number }) {
  const total = Math.max(1, tin + tout);
  return (
    <div className={s.tokens}>
      <div className={s.tokBar} role="img" aria-label={`${tin} tokens in (${cached} cached), ${tout} out`}>
        <span className={s.tokCached} style={{ width: `${(cached / total) * 100}%` }} />
        <span className={s.tokIn} style={{ width: `${((tin - cached) / total) * 100}%` }} />
        <span className={s.tokOut} style={{ width: `${(tout / total) * 100}%` }} />
      </div>
      <dl className={s.kv3}>
        <div><dt>In</dt><dd>{tin.toLocaleString("en")}</dd></div>
        <div><dt><i className={s.swCached} />Cached</dt><dd>{cached.toLocaleString("en")}</dd></div>
        <div><dt><i className={s.swOut} />Out</dt><dd>{tout.toLocaleString("en")}</dd></div>
      </dl>
    </div>
  );
}

const TRIGGER_LABEL = { always: "Always", tool_call: "Tool call", gated: "Gated" } as const;

/** D-59 Knowledge: every passage retrieved for this turn; cited ones carry their [n], the rest are dimmed. */
function KnowledgeList({ k, m, armed }: { k: NonNullable<TurnTrace["knowledge"]>; m: Message; armed: boolean }) {
  const rows = [...k.retrieved].sort((a, b) => (a.cited && b.cited ? (a.n ?? 0) - (b.n ?? 0) : a.cited === b.cited ? b.score - a.score : a.cited ? -1 : 1));
  const sources = useKnowledge(m.author.characterId).data;
  const types = new Map<string, Citation["type"]>([
    ...(sources ?? []).map((x) => [x.id, x.type] as const),
    ...(m.citations ?? []).map((c) => [c.sourceId, c.type] as const),
  ]);
  return (
    <>
      {k.query && <p className={s.kQuery}><span>Query</span>“{k.query}”</p>}
      <ul className={s.kList}>
        {rows.map((r) => {
          const cite = r.cited ? m.citations?.find((c) => c.chunkId === r.chunkId) : undefined;
          const type = types.get(r.sourceId) ?? (/\.[a-z]{2,4}$/i.test(r.title) ? "file" : "text");
          const open = () => (cite
            ? openCitation(cite, m.author.characterId)
            : openCitation({ n: r.n ?? 0, sourceId: r.sourceId, chunkId: r.chunkId, title: r.title, locator: r.locator, quote: r.text }, m.author.characterId));
          return (
            <li key={r.chunkId}>
              <button
                type="button"
                className={cx(s.kRow, !r.cited && s.kUnused)}
                onClick={open}
                aria-label={`${r.cited ? `Cited [${r.n}]` : "Retrieved, not used"}: ${r.title}${r.locator ? `, ${r.locator}` : ""}, score ${r.score.toFixed(2)}. Open source`}
              >
                <span className={s.kN} aria-hidden="true">{r.cited ? r.n : "–"}</span>
                <span className={s.kMain}>
                  <span className={s.kTitle}>
                    <TypeGlyph type={type} title={r.title} />
                    <span className={s.kName}>{r.title}</span>
                    {r.locator && <span className={s.kLoc}>{r.locator}</span>}
                  </span>
                  <span className={s.kText}>{r.text}</span>
                  <span className={s.kScore}>
                    <span className={s.kTrack} aria-hidden="true"><span className={s.kFill} style={{ transform: `scaleX(${armed ? r.score : 0})` }} /></span>
                    <b>{r.score.toFixed(2)}</b>
                    {!r.cited && <em className={s.kTag}>retrieved · not used</em>}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </>
  );
}

function SpeakerHead({ m, c, live }: { m: Message; c?: Character; live: boolean }) {
  const text = plainText(useStreamText(m.status === "streaming" ? m.id : null) ?? m.content).replace(/\s+/g, " ");
  if (!c) return null;
  const emotion = m.emotion ?? "neutral";
  const meta = emotionMeta[emotion];
  const where = m.debate ? `R${m.debate.round} · ${m.debate.phase}${m.debate.side ? ` · ${m.debate.side === "prop" ? "Prop" : "Opp"}` : ""}` : `#${m.seq}`;
  return (
    <PaletteScope paletteId={c.paletteId} className={s.speaker}>
      <PortraitCard character={c} emotion={emotion} size="head" width={72} parallax={false} />
      <div className={s.spText}>
        <div className={s.spTop}>
          <span className={s.spName}>{firstName(c.profile.name)}</span>
          <span className={s.spEmo}><span aria-hidden="true">{meta.icon}</span> {meta.label}</span>
        </div>
        <span className={s.spWhere}>{where}{live && <span className={s.liveDot}> · thinking…</span>}</span>
        <p className={s.spQuote}>“{text.length > 120 ? `${text.slice(0, 118).trimEnd()}…` : text || "…"}”</p>
      </div>
    </PaletteScope>
  );
}

export function InsightDrawer({ sessionId, close }: OverlayComponentProps<"O08">) {
  const { runtime, replay } = useSlotRuntime(sessionId);
  const chars = useStore(entities, (st) => st.chars);
  const presenter = usePrefs((p) => p.presenterMode);
  const { reduced } = useMotionPrefs();
  const selected = useUi((u) => u.insight.messageId);
  const [fetched, setFetched] = useState<Record<string, TurnTrace | null>>({});
  useShortcut("i", close);

  const list = useMemo(() => (runtime ? runtime.order.map((id) => runtime.messages[id]).filter(Boolean) : []), [runtime]);
  const charIds = useMemo(() => list.filter(isChar).map((m) => m.id), [list]);
  // Follow the latest finished reply (its trace is complete) unless the user picked one; a reply streaming right
  // now shows as a LIVE strip on top that can be selected.
  const liveMsg = runtime?.streamingId ? runtime.messages[runtime.streamingId] : undefined;
  const latestDone = [...charIds].reverse().find((id) => runtime?.messages[id]?.status !== "streaming") ?? charIds[charIds.length - 1];
  const msgId = selected && runtime?.messages[selected] ? selected : latestDone;
  const m = msgId ? runtime?.messages[msgId] : undefined;
  const idx = m ? charIds.indexOf(m.id) : -1;

  useEffect(() => {
    if (!m || m.trace || m.status === "streaming" || !isChar(m) || m.id in fetched) return;
    let p = traceCache.get(m.id);
    if (!p) {
      p = client.sessions.trace(m.id).catch(() => null);
      traceCache.set(m.id, p);
    }
    const id = m.id;
    void p.then((t) => setFetched((f) => ({ ...f, [id]: t })));
  }, [m, fetched]);

  const armed = useArmed(reduced ? "static" : `${m?.id}:${m?.trace ? 1 : 0}`) || reduced;
  const go = (d: number) => {
    const next = charIds[Math.max(0, Math.min(charIds.length - 1, (idx < 0 ? charIds.length - 1 : idx) + d))];
    if (next) selectInsight(next);
  };

  const c = m?.author.characterId ? chars[m.author.characterId] : undefined;
  const trace = m?.trace ?? (m ? fetched[m.id] ?? undefined : undefined);
  const streaming = m?.status === "streaming";
  const nameOf = (id: string) => firstName(chars[id]?.profile.name) || id;
  const compact = presenter;
  const firstCast = runtime?.session.participants[0]?.characterId;

  let body: ReactNode;
  if (!runtime) body = <p className={s.empty}>Open a session to see how the cast thinks.</p>;
  else if (!m) body = <p className={s.empty}>Send a message to see how {nameOf(firstCast ?? "") || "they"} think{firstCast ? "s" : ""}.</p>;
  else if (!isChar(m)) body = <p className={s.empty}>Insight is available for character messages.</p>;
  else {
    let i = 0;
    const num = (x: number) => String(x + 1).padStart(2, "0");
    const r = trace?.routing;
    const e = trace?.emotion;
    const md = trace?.model;
    const en = trace?.energy;
    const sections: ReactNode[] = [];
    if (r) {
      const cands = [...(r.candidates ?? [])].sort((a, b) => b.p - a.p);
      sections.push(
        <Section key="routing" n={num(i)} title="Routing · who speaks" i={i++} aside={r.forcedBy ? <Tape tone={r.forcedBy === "round_order" ? "ink" : "brand"} size="sm">{FORCED_LABEL[r.forcedBy]}</Tape> : null}>
          {r.question && <p className={s.question}>{r.question}</p>}
          {cands.length > 0 ? (
            <div className={s.bars}>
              {cands.map((x) => (
                <PaletteScope key={x.characterId} paletteId={chars[x.characterId]?.paletteId} className={cx(s.barRow, x.characterId === r.selected && s.barPicked)}>
                  <ProbBar label={<>{x.characterId === r.selected && <span className={s.pick} aria-label="selected">▸</span>}{nameOf(x.characterId)}</>} p={armed ? r2(x.p) : 0} />
                </PaletteScope>
              ))}
            </div>
          ) : (
            <p className={s.kvLine}><span>Selected</span><b>{nameOf(r.selected)}</b></p>
          )}
          {r.skipped?.length ? <p className={s.skipped}>Skipped: {r.skipped.map((x) => `${nameOf(x.characterId)} (${x.reason === "exhausted" ? "asleep" : x.reason})`).join(", ")}</p> : null}
          {r.reason && <p className={s.reason}>{r.reason}</p>}
        </Section>,
      );
    }
    if (e) {
      const cands = [...(e.candidates ?? [])].sort((a, b) => b.p - a.p).slice(0, 3);
      sections.push(
        <Section key="emotion" n={num(i)} title="Emotion" i={i++} aside={<span className={s.chip}>{e.source === "llm" ? "AI" : e.source}</span>}>
          <p className={s.chosen}><span className={s.chosenIcon} aria-hidden="true">{emotionMeta[e.chosen].icon}</span>{emotionMeta[e.chosen].label}{cands[0] && <span className={cx(s.band, s[`band_${probBand(r2(cands[0].p))}`])}>{probBand(r2(cands[0].p))}</span>}</p>
          {cands.length > 0 && (
            <div className={s.bars}>
              {cands.map((x) => (
                <ProbBar key={x.label} label={<><span className={s.emoIcon} aria-hidden="true">{emotionMeta[x.label].icon}</span>{emotionMeta[x.label].label}</>} p={armed ? r2(x.p) : 0} color={x.label === e.chosen ? undefined : "var(--paper-300)"} />
              ))}
            </div>
          )}
          {runtime.session.emotionMode === "user" && <p className={s.fine}>MANUAL mode: recorded here, not shown on the portrait.</p>}
        </Section>,
      );
    }
    if (md) {
      const cached = md.tokensCached ?? 0;
      const hit = trace?.context?.cacheHitPct ?? (md.tokensIn ? Math.round((cached / md.tokensIn) * 100) : 0);
      sections.push(
        <Section key="model" n={num(i)} title="Model" i={i++} aside={<>
          {md.pricePeriod && <Tape tone={md.pricePeriod === "peak" ? "warn" : "ink"} size="sm">{md.pricePeriod === "peak" ? "Peak" : "Off-peak"}</Tape>}
          {hit > 0 && <span className={s.cache}>Cache {hit}%</span>}
        </>}>
          <p className={s.modelId}><b>{md.id}</b><span> · {md.provider}{md.quantization ? ` · ${md.quantization}` : ""}</span></p>
          <LatencyBar first={md.latencyMs.firstToken} total={md.latencyMs.total} armed={armed} />
          <TokenSplit tin={md.tokensIn} cached={cached} tout={md.tokensOut} />
          <p className={s.cost}><span>Cost</span><b>{formatUsd(md.costUsd)}</b></p>
        </Section>,
      );
    }
    if (en) {
      const pct = en.max ? Math.min(1, en.remaining / en.max) : 0;
      sections.push(
        <Section key="energy" n={num(i)} title="Energy" i={i++}>
          <PaletteScope paletteId={chars[en.characterId]?.paletteId} className={s.energy}>
            <span className={s.drain}>−{en.spent} ⚡</span>
            <span className={s.remain}>{en.remaining.toLocaleString("en")} / {en.max.toLocaleString("en")}</span>
            <span className={s.eTrack} aria-hidden="true"><span className={cx(s.eFill, pct < 0.2 ? s.eRed : pct < 0.4 ? s.eAmber : null)} style={{ transform: `scaleX(${armed ? pct : 0})` }} /></span>
          </PaletteScope>
        </Section>,
      );
    }
    if (!compact) {
      if (trace?.memory?.recalled.length) {
        sections.push(
          <Section key="memory" n={num(i)} title="Memory recalled" i={i++}>
            <ul className={s.recall}>
              {trace.memory.recalled.map((x) => (
                <li key={x.memoryItemId}><span>{x.text}</span>{x.score !== undefined && <b>{x.score.toFixed(2)}</b>}</li>
              ))}
            </ul>
          </Section>,
        );
      }
    }
    if (trace?.knowledge?.retrieved.length) {
      const kn = trace.knowledge;
      const used = kn.retrieved.filter((x) => x.cited).length;
      sections.push(
        <Section key="knowledge" n={num(i)} title="Knowledge" i={i++} aside={<>
          {kn.trigger && <span className={s.chip}>{TRIGGER_LABEL[kn.trigger]}</span>}
          <span className={s.kUsed}>{used}/{kn.retrieved.length} cited</span>
        </>}>
          <KnowledgeList k={kn} m={m} armed={armed} />
        </Section>,
      );
    }
    if (!compact) {
      if (trace?.contextInSession?.length) {
        sections.push(
          <Section key="recall" n={num(i)} title="In-session recall" i={i++}>
            <ul className={s.recall}>
              {trace.contextInSession.map((x) => (
                <li key={x.messageId}>
                  <button type="button" className={s.recallBtn} onClick={() => runtime.messages[x.messageId] && isChar(runtime.messages[x.messageId]) && selectInsight(x.messageId)}>“{x.text}”</button>
                </li>
              ))}
            </ul>
          </Section>,
        );
      }
      if (trace?.context) {
        const u = trace.context.used;
        sections.push(
          <Section key="context" n={num(i)} title="Context budget" i={i++}>
            <StackedBar
              label="Context budget"
              total={trace.context.budget}
              segments={(Object.keys(u) as (keyof typeof u)[]).filter((k) => u[k] > 0).map((k) => ({ key: k, label: k, value: u[k], color: CONTEXT_COLORS[k] }))}
            />
          </Section>,
        );
      }
      if (trace?.guardrail?.checks.length) {
        sections.push(
          <Section key="guard" n={num(i)} title="Guardrail" i={i++}>
            <ul className={s.checks}>
              {trace.guardrail.checks.map((x) => (
                <li key={x.name} className={s[`v_${x.verdict}`]}>
                  <span className={s.vMark} aria-hidden="true">{x.verdict === "pass" ? "✓" : "!"}</span>
                  <span className={s.vName}>{x.name}</span>
                  <span className={s.vVerdict}>{x.verdict}{x.p !== undefined ? ` · ${x.p.toFixed(2)}` : ""}</span>
                </li>
              ))}
            </ul>
          </Section>,
        );
      }
    }
    body = (
      <div className={s.stack} key={m.id}>
        {isChar(liveMsg) && liveMsg.id !== m.id && (
          <button type="button" className={s.liveStrip} onClick={() => selectInsight(liveMsg.id)}>
            <span className={s.liveBadge}>{replay ? "● Now" : "● Live"}</span>
            <span>{nameOf(liveMsg.author.characterId!)} is replying</span>
            <span className={s.liveScan} aria-hidden="true" />
          </button>
        )}
        <SpeakerHead m={m} c={c} live={streaming} />
        <Pipeline trace={trace} streaming={streaming} />
        {sections.length ? sections : (
          <p className={s.empty}>{streaming ? "Reading the trace as the reply streams…" : "No trace was recorded for this reply."}</p>
        )}
      </div>
    );
  }

  return (
    <Drawer
      title="Insight"
      width={compact ? 300 : 400}
      onClose={close}
      className={cx(s.drawer, compact && s.compact)}
      headerExtra={charIds.length > 0 ? (
        <span className={s.nav}>
          <IconButton label="Previous reply" size="sm" disabled={idx <= 0} onClick={() => go(-1)}>‹</IconButton>
          <span className={s.navCount}>{idx >= 0 ? idx + 1 : charIds.length}/{charIds.length}</span>
          <IconButton label="Next reply" size="sm" disabled={idx < 0 || idx >= charIds.length - 1} onClick={() => go(1)}>›</IconButton>
        </span>
      ) : null}
    >
      {body}
    </Drawer>
  );
}
