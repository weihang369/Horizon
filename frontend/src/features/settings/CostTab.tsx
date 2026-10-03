// Settings → Cost (SET-06/07/08) and the Spend view (SET-09): generation mode, cost toggles, daily / creation caps,
// warn %, default character energy; spend today and to date by category, character and session, estimated vs actual.
// Owner: Builder A.
import { useEffect, useState } from "react";
import { client } from "../../client";
import { useCharacter, useUsage } from "../../client/hooks";
import type { AppSettings, UsageRecord } from "../../contract/types";
import { formatUsd } from "../../domain/format";
import { Segmented, Toggle } from "../../ui/Controls";
import { Skeleton, StackedBar } from "../../ui/Data";
import { TextField } from "../../ui/Fields";
import { EmptyState } from "../../ui/Panels";
import { Tape } from "../../ui/Tape";
import { Row, Section, useSettingsPatch } from "./parts";
import { spendRows } from "./spend";
import s from "./Settings.module.css";

type View = "controls" | "spend";

export function CostTab({ settings }: { settings: AppSettings }) {
  const [view, setView] = useState<View>("controls");
  return (
    <>
      <div className={s.viewSwitch}>
        <Segmented<View> label="Cost view" className="hz-cost-view" value={view} onChange={setView} options={[{ value: "controls", label: "Controls" }, { value: "spend", label: "Spend" }]} />
      </div>
      {view === "controls" ? <Controls settings={settings} /> : <SpendView capUsd={settings.budget.dailyCapUsd} />}
    </>
  );
}

function MoneyField({ label, value, onCommit, step = 0.1, suffix = "US$" }: { label: string; value: number; onCommit: (v: number) => void; step?: number; suffix?: string }) {
  const [text, setText] = useState(String(value));
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => setText(String(value)), [value]);
  const commit = () => {
    const n = Number(text);
    if (!Number.isFinite(n) || n <= 0) return setErr("Enter a positive number.");
    setErr(null);
    if (n !== value) onCommit(n);
  };
  return (
    <div className={s.money}>
      <span className={s.moneyPrefix} aria-hidden="true">{suffix}</span>
      <TextField label={label} hideLabel type="number" inputMode="decimal" step={step} min={0} value={text} error={err} onChange={(e) => setText(e.target.value)} onBlur={commit} onKeyDown={(e) => e.key === "Enter" && commit()} />
    </div>
  );
}

function Controls({ settings }: { settings: AppSettings }) {
  const { save } = useSettingsPatch();
  const c = settings.cost;
  return (
    <>
      <Section title="Generation mode" desc="How much Horizon generates when you create a character.">
        <div className={s.modeCards} role="radiogroup" aria-label="Generation mode">
          {(["lean", "standard"] as const).map((m) => (
            <button key={m} type="button" role="radio" aria-checked={settings.generationMode === m} className={s.modeCard} onClick={() => void save({ generationMode: m })}>
              <span className={s.modeName}>{m === "lean" ? "Lean" : "Standard"}{m === "lean" && <Tape tone="ok" size="sm">DEFAULT</Tape>}</span>
              <span className={s.modeDesc}>{m === "lean" ? "1 candidate portrait, 4 emotions. The rest on demand." : "2 candidate portraits, all 7 emotions at creation."}</span>
              <span className={s.modeCost}>{m === "lean" ? "≈ $0.20 per character" : "≈ $0.40 per character"}</span>
            </button>
          ))}
        </div>
        <Row label="Auto-generate missing emotions" desc="Fill empty emotion slots in the background when a character first needs them.">
          <Toggle label="Auto-generate missing emotions" hideLabel checked={settings.autoGenerateMissingEmotions} onChange={(v) => void save({ autoGenerateMissingEmotions: v })} />
        </Row>
      </Section>
      <Section title="Budget & energy" desc="There is no per-session cap: each character's ⚡ energy keeps conversations cheap.">
        <Row label="Daily cap" desc={`Spent today: ${formatUsd(settings.spentTodayUsd)}. At 100 % Horizon pauses and asks.`}>
          <MoneyField label="Daily cap in US dollars" value={settings.budget.dailyCapUsd} onCommit={(v) => void save({ budget: { dailyCapUsd: v } }, "Daily cap updated.")} />
        </Row>
        <Row label="Per-character creation cap" desc="Most a single character's portraits, emotions and song may cost.">
          <MoneyField label="Creation cap in US dollars" value={settings.budget.perCharacterCreationCapUsd} onCommit={(v) => void save({ budget: { perCharacterCreationCapUsd: v } }, "Creation cap updated.")} />
        </Row>
        <Row label="Warn at" desc="A toast when spend reaches this share of a cap.">
          <Segmented label="Warn at" value={String(settings.budget.warnAtPct)} onChange={(v) => void save({ budget: { warnAtPct: Number(v) } })} options={["50", "80", "90"].map((v) => ({ value: v, label: `${v} %` }))} />
        </Row>
        <Row label="Default character energy" desc="⚡ per day for new characters (1 ⚡ = US$0.0001). Each profile can override it.">
          <Segmented label="Default character energy" value={String(settings.energy.defaultMaxPoints)} onChange={(v) => void save({ energy: { defaultMaxPoints: Number(v) } })} options={["500", "1000", "2000"].map((v) => ({ value: v, label: `${v} ⚡` }))} />
        </Row>
      </Section>
      <Section title="Cost display">
        <Row label="Show cost estimates" desc="“≈ $0.04” on buttons that spend.">
          <Toggle label="Show cost estimates" hideLabel checked={c.showEstimates} onChange={(v) => void save({ cost: { showEstimates: v } })} />
        </Row>
        <Row label="Confirm before generating" desc="The first generation each launch asks first.">
          <Toggle label="Confirm before generating" hideLabel checked={c.confirmBeforeGenerate} onChange={(v) => void save({ cost: { confirmBeforeGenerate: v } })} />
        </Row>
        <Row label="Cost HUD" desc="Running session cost in the session header.">
          <Toggle label="Cost HUD" hideLabel checked={c.showHud} onChange={(v) => void save({ cost: { showHud: v } })} />
        </Row>
      </Section>
    </>
  );
}

// ── Spend view (SET-09) ──────────────────────────────────────────────────────
const CAT_COLOR: Record<UsageRecord["category"], string> = {
  chat: "var(--horizon-500)", decision: "var(--horizon-300)", image: "var(--signal-ok)", music: "var(--blush)",
  profile: "var(--signal-warn)", summary: "var(--paper-300)", memory: "var(--sad-blue)", embedding: "var(--ink-500)", energy_topup: "var(--energy-amber)",
};
const CAT_LABEL: Record<UsageRecord["category"], string> = {
  chat: "Chat", decision: "Decision", image: "Images", music: "Music", profile: "Profiles", summary: "Summaries", memory: "Memory", embedding: "Embeddings", energy_topup: "Top-ups",
};

function SpendView({ capUsd }: { capUsd: number }) {
  const { data, loading } = useUsage();
  if (loading || !data) return <Skeleton lines={5} />;
  const { summary, records } = data;
  if (!records.length || summary.totalUsd === 0) return <EmptyState title="No spending yet" body="Everything so far was free." />;
  const delta = summary.actualUsd - summary.estimatedUsd;
  const todayPct = Math.min(1, summary.todayUsd / Math.max(capUsd, 0.0001));
  const cats = (Object.keys(summary.byCategory) as UsageRecord["category"][]).filter((k) => summary.byCategory[k] > 0).sort((a, b) => summary.byCategory[b] - summary.byCategory[a]);
  const chars = spendRows(summary.byCharacter, 6);
  const sessions = spendRows(summary.bySession, 6);
  return (
    <>
      <div className={s.tiles}>
        <div className={s.tile}>
          <span className={s.tileLabel}>Today</span>
          <span className={s.tileValue}>{formatUsd(summary.todayUsd)}</span>
          <span className={s.tileMeter}><i style={{ transform: `scaleX(${todayPct})` }} /></span>
          <span className={s.tileSub}>of {formatUsd(capUsd)} daily cap</span>
        </div>
        <div className={s.tile}>
          <span className={s.tileLabel}>To date</span>
          <span className={s.tileValue}>{formatUsd(summary.totalUsd)}</span>
          <span className={s.tileSub}>{records.length} ledger entries</span>
        </div>
        <div className={s.tile}>
          <span className={s.tileLabel}>Estimated vs actual</span>
          <span className={s.tileValue} data-delta={delta > 0 ? "over" : "under"}>{delta >= 0 ? "+" : "−"}{formatUsd(Math.abs(delta))}</span>
          <span className={s.tileSub}>est. {formatUsd(summary.estimatedUsd)} · actual {formatUsd(summary.actualUsd)}</span>
        </div>
      </div>
      <Section title="By category">
        <StackedBar label="Spend by category" format={(n) => formatUsd(n)} segments={cats.map((k) => ({ key: k, label: CAT_LABEL[k], value: summary.byCategory[k], color: CAT_COLOR[k] }))} />
      </Section>
      <div className={s.split2}>
        <Section title="By character">
          <ol className={s.bars}>{chars.map((r) => <CharBar key={r.id} id={r.id} usd={r.usd} max={chars[0].usd} />)}</ol>
        </Section>
        <Section title="By session">
          <ol className={s.bars}>{sessions.map((r) => <SessionBar key={r.id} id={r.id} usd={r.usd} max={sessions[0].usd} />)}</ol>
        </Section>
      </div>
    </>
  );
}

function Bar({ name, usd, max }: { name: string; usd: number; max: number }) {
  return (
    <li className={s.bar}>
      <span className={s.barName}>{name}</span>
      <span className={s.barTrack}><i style={{ transform: `scaleX(${max ? usd / max : 0})` }} /></span>
      <span className={s.barValue}>{formatUsd(usd)}</span>
    </li>
  );
}
function CharBar({ id, usd, max }: { id: string; usd: number; max: number }) {
  const c = useCharacter(id).data;
  return <Bar name={c?.profile.name ?? "Deleted character"} usd={usd} max={max} />;
}
function SessionBar({ id, usd, max }: { id: string; usd: number; max: number }) {
  const [title, setTitle] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    client.sessions.get(id).then((x) => alive && setTitle(x.session.title)).catch(() => alive && setTitle("Deleted session"));
    return () => {
      alive = false;
    };
  }, [id]);
  return <Bar name={title ?? "…"} usd={usd} max={max} />;
}
