// S11 Verdict (MULTI-08) — Builder D. Full-bleed card driven by session.state.verdict (D-51/D-57 events):
// "STRONGER CASE: {side}" (arbiter or You decide) · "TOO CLOSE TO CALL" · "SUMMARY" (panel / none).
// Reveal (VMD §2.4, skippable, D-55): 300 bars grow + count up · 1100 tension · 1500 slam + sting, winner 1.03,
// loser under .35 ink · 2300 bullets · 2600 the winner's theme (else Arena continues, MUS-08).
// You decide: summary first, then two 480×120 side buttons; the pick triggers the reveal (AC3, D-48).
import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { client } from "../../client";
import { useCharacters, useSessionRuntime } from "../../client/hooks";
import type { Character, DebateConfig, DebateState, Message, Side, ThemeSong, Verdict } from "../../contract/types";
import { reportError, run } from "../../app/errors";
import { toast } from "../../app/layers";
import { useShortcut } from "../../app/shortcuts";
import { audio } from "../../audio/engine";
import { PortraitCard } from "../../character";
import { verdictWinnerTheme } from "../../engine/musicDirector";
import type { MusicCast } from "../../engine/musicDirector";
import { playCeremony, useCeremony, useMotionPrefs } from "../../motion";
import type { Route } from "../../router";
import { back, navigate } from "../../router";
import { PaletteScope } from "../../theme";
import { BackIcon, Button, IconButton, RansomText, ScanLoader, Tape, Toggle, cx } from "../../ui";
import { SIDE_NAME, debateColumns, rubricRows, verdictHeadline } from "./shared";
import s from "./VerdictScreen.module.css";

const REVEAL_MS = 2600;
const ARENA = { url: "placeholder:system/arena", label: "Arena" };
let revealN = 0;

export function VerdictScreen({ route }: { route: Extract<Route, { name: "verdict" }> }) {
  const rt = useSessionRuntime(route.sessionId);
  const castQ = useCharacters(route.worldId, { includeArchived: true });
  const chars = useMemo(() => Object.fromEntries((castQ.data ?? []).map((c) => [c.id, c])), [castQ.data]);
  const session = rt.session;
  const cfg = (session?.config ?? null) as DebateConfig | null;
  const st = (session?.state ?? null) as DebateState | null;
  const verdict = st?.verdict ?? null;
  const cols = useMemo(() => debateColumns(session?.participants ?? [], cfg), [session?.participants, cfg]);
  const panel = cfg?.format === "panel";
  const youDecide = cfg?.verdictBy === "user" && !verdict && !panel;
  const waiting = !verdict && !youDecide && (st?.phase === "verdict" || session?.status === "active");

  if (rt.status === "error") {
    return (
      <main className={s.empty}>
        <Tape tone="error">Warning</Tape>
        <p>{rt.error?.message ?? "This verdict can't be opened."}</p>
        <Button onClick={() => back()}>◂ Back</Button>
      </main>
    );
  }
  if (!session || !cfg) return <main className={s.empty} aria-busy="true"><ScanLoader label="Loading verdict" /></main>;
  if (session.mode !== "debate") {
    return (
      <main className={s.empty}>
        <p>Only debates have a verdict.</p>
        <Button onClick={() => navigate({ name: "session", worldId: route.worldId, sessionId: route.sessionId })}>Open session ▸</Button>
      </main>
    );
  }

  return (
    <main className={s.root} data-screen="verdict">
      <header className={s.top}>
        <IconButton label="Back" size="sm" onClick={() => back()}><BackIcon /></IconButton>
        <Tape tone="ink" size="sm">Verdict</Tape>
        <p className={s.motionLine}><span>Motion</span>{cfg.motion}</p>
      </header>
      {verdict ? (
        <Reveal key={verdictKey(verdict)} verdict={verdict} cfg={cfg} cols={cols} chars={chars} list={rt.list} worldId={route.worldId} sessionId={route.sessionId} title={session.title} />
      ) : youDecide ? (
        <YouDecide cols={cols} chars={chars} list={rt.list} sessionId={route.sessionId} />
      ) : waiting ? (
        <div className={s.deliberating} role="status">
          <RansomText text="DELIBERATING" size={56} tone="mixed" />
          <p>The arbiter is weighing argument quality, not who's factually right.</p>
          <ScanLoader label="Arbiter at work" />
        </div>
      ) : (
        <div className={s.deliberating} role="status">
          <RansomText text="NO VERDICT" size={56} tone="mixed" />
          <p>This debate ended without a verdict. The transcript is still yours.</p>
        </div>
      )}
      {!youDecide && (
        <Actions sessionId={route.sessionId} worldId={route.worldId} cfg={cfg} cast={session.participants.map((p) => p.characterId)} verdict={verdict} chars={chars} />
      )}
    </main>
  );
}

const verdictKey = (v: Verdict) => `${v.decidedBy}:${v.strongerCase ?? "x"}`;

// ── Reveal ───────────────────────────────────────────────────────────────────
interface RevealProps {
  verdict: Verdict; cfg: DebateConfig; cols: { prop: string[]; opp: string[] }; chars: Record<string, Character>;
  list: Message[]; worldId: string; sessionId: string; title: string;
}

function Reveal({ verdict, cfg, cols, chars }: RevealProps) {
  const panel = cfg.format === "panel";
  const head = verdictHeadline(verdict, cfg.format);
  const [id] = useState(() => `S11:reveal:${++revealN}`);
  const { active, skipped } = useCeremony(id);
  const { reduced } = useMotionPrefs();
  const [started, setStarted] = useState(false);
  const end = skipped || (started && !active) || reduced;
  const [showArbiter, setShowArbiter] = useState(verdict.decidedBy !== "user");

  // Ceremony + timed sounds (skippable; sounds stop on skip).
  useEffect(() => {
    let h: { skip(): void } | null = null;
    const timers: number[] = [];
    const t = window.setTimeout(() => {
      setStarted(true);
      h = playCeremony(id, { durationMs: REVEAL_MS, onSkip: () => timers.forEach(clearTimeout) });
      if (head.kind !== "summary") timers.push(window.setTimeout(() => audio.playSfx("verdict_tension"), 1100));
      if (head.kind === "side") timers.push(window.setTimeout(() => audio.playSfx("verdict_sting"), 1500));
    }, 0);
    return () => {
      clearTimeout(t);
      timers.forEach(clearTimeout);
      h?.skip();
    };
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Music at the end of the reveal: the winner's theme, else Arena continues (MUS-08).
  useWinnerMusic(end, verdict, cfg, cols, chars);

  const sideIds = (side: Side) => cols[side];
  const winner = head.kind === "side" ? head.side : null;
  const loser: Side | null = winner ? (winner === "prop" ? "opp" : "prop") : null;
  const subjects = verdict.scoresBy === "debater" || panel ? [...cols.prop, ...cols.opp] : ["prop", "opp"];
  const rows = rubricRows(verdict, cfg.rubric, subjects);
  const showBars = rows.length > 0 && (verdict.decidedBy !== "user" || showArbiter);
  const summaries = orderSummaries(verdict, panel ? [...cols.prop, ...cols.opp] : ["prop", "opp"]);

  const stack = (side: Side) => {
    const ids = sideIds(side);
    const role = winner === side ? "win" : loser === side ? "lose" : "even";
    return (
      <aside className={cx(s.stack, s[`stack_${side}`])} data-role={role} aria-label={panel ? "Panel" : SIDE_NAME[side]}>
        {!panel && <Tape tone={side} size="md" rotate={side === "prop" ? -3 : 3}>{SIDE_NAME[side]}</Tape>}
        <div className={s.cards}>
          {ids.map((cid, i) => {
            const c = chars[cid];
            if (!c) return null;
            return (
              <div key={cid} className={s.card} style={{ "--i": i, "--n": ids.length } as CSSProperties}>
                <PortraitCard
                  character={ids.length > 1 ? { ...c, profile: { ...c.profile, name: c.profile.name.split(" ")[0] } } : c}
                  plateSubtitle={ids.length > 1 ? null : undefined}
                  emotion={role === "win" && end ? "happy" : role === "lose" && end ? "sad" : "neutral"}
                  size="stage"
                  width="var(--v-card)"
                  showPlate
                  dimmed={role === "lose" && end}
                  speaking={role === "win" && end}
                  parallax={false}
                />
              </div>
            );
          })}
        </div>
      </aside>
    );
  };

  return (
    <div className={cx(s.reveal, end && s.end)} data-kind={head.kind} data-winner={winner ?? undefined}>
      <div className={s.flash} aria-hidden="true" />
      <section className={s.banner} aria-live="polite">
        <div className={cx(s.bannerTape, winner && s[`banner_${winner}`], head.kind === "tie" && s.bannerTie)}>
          {head.kind === "side" && <span className={s.kicker}>Stronger case</span>}
          <RansomText
            key={end ? "e" : "p"}
            text={head.kind === "side" ? SIDE_NAME[head.side].toUpperCase() : head.text}
            size="var(--banner-size)"
            tone="mixed"
            slam={!end}
            delayMs={1500}
            staggerMs={34}
          />
          <span className="sr-only">{head.text}</span>
        </div>
        <p className={s.sub}>{head.sub}</p>
      </section>

      <div className={s.main}>
        {stack("prop")}
        <div className={s.centre}>
          {rows.length > 0 && verdict.decidedBy === "user" && (
            <Toggle checked={showArbiter} onChange={setShowArbiter} label="Show Arbiter's view" className={s.arbToggle} />
          )}
          {showBars && (
            <section className={s.rubric} aria-label="Rubric scores">
              <div className={s.legend} aria-hidden="true">
                {subjects.map((sid) => (
                  <span key={sid} className={s.legendItem} data-subject={sid in SIDE_NAME ? sid : undefined}>
                    <SubjectSwatch sid={sid} chars={chars} />
                    {sid in SIDE_NAME ? SIDE_NAME[sid as Side] : chars[sid]?.profile.name.split(" ")[0]}
                  </span>
                ))}
              </div>
              {rows.map((r, ri) => (
                <div key={r.id} className={s.row}>
                  <span className={s.crit}>{r.label}</span>
                  <div className={s.bars}>
                    {r.values.map((v, vi) => (
                      <PaletteScope key={v.subjectId} paletteId={sideOrPalette(v.subjectId, chars)} className={s.barRow}>
                        <span className={s.track}>
                          <span
                            className={cx(s.fill, v.subjectId === "prop" && s.fillProp, v.subjectId === "opp" && s.fillOpp)}
                            style={{ "--v": v.value / 10, "--d": `${300 + (ri * r.values.length + vi) * 120}ms` } as CSSProperties}
                          />
                        </span>
                        <CountUp value={v.value} delay={300 + (ri * r.values.length + vi) * 120} end={end} />
                      </PaletteScope>
                    ))}
                  </div>
                </div>
              ))}
            </section>
          )}

          <section className={cx(s.summaries, summaries.length > 2 && s.summaries3)}>
            {summaries.map((x, i) => (
              <div key={x.subjectId} className={s.summary} style={{ "--d": `${2300 + i * 80}ms` } as CSSProperties}>
                <h3 className={s.sumHead}>
                  {x.subjectId in SIDE_NAME
                    ? <Tape tone={x.subjectId as Side} size="sm">{SIDE_NAME[x.subjectId as Side]}</Tape>
                    : <PaletteScope paletteId={chars[x.subjectId]?.paletteId} as="span" className={s.sumName}>{chars[x.subjectId]?.profile.name ?? x.subjectId}</PaletteScope>}
                </h3>
                <ul>
                  {x.points.map((pt, j) => <li key={j}>{pt}</li>)}
                </ul>
              </div>
            ))}
          </section>

          {verdict.keyDisagreement && (
            <div className={s.key} style={{ "--d": "2450ms" } as CSSProperties}>
              <Tape tone="ink" size="sm">Key disagreement</Tape>
              <p>{verdict.keyDisagreement}</p>
            </div>
          )}
          {verdict.rationale && (
            <p className={s.rationale} style={{ "--d": "2550ms" } as CSSProperties}>
              <span>Rationale</span>
              {verdict.rationale}
            </p>
          )}
        </div>
        {stack("opp")}
      </div>
    </div>
  );
}

function SubjectSwatch({ sid, chars }: { sid: string; chars: Record<string, Character> }) {
  if (sid === "prop" || sid === "opp") return <i className={cx(s.sw, sid === "prop" ? s.swProp : s.swOpp)} />;
  return <PaletteScope paletteId={chars[sid]?.paletteId} as="i" className={s.sw} />;
}

const sideOrPalette = (sid: string, chars: Record<string, Character>) => (sid === "prop" || sid === "opp" ? null : chars[sid]?.paletteId);

function orderSummaries(v: Verdict, order: string[]) {
  const by = new Map(v.summary.map((x) => [x.subjectId, x]));
  const out = order.map((id) => by.get(id)).filter((x): x is Verdict["summary"][number] => !!x);
  for (const x of v.summary) if (!order.includes(x.subjectId)) out.push(x);
  return out;
}

function CountUp({ value, delay, end }: { value: number; delay: number; end: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (end) {
      el.textContent = value.toFixed(1);
      return;
    }
    let raf = 0;
    const t0 = performance.now() + delay;
    const tick = (now: number) => {
      const k = Math.min(1, Math.max(0, (now - t0) / 600));
      el.textContent = (value * (1 - Math.pow(1 - k, 3))).toFixed(1);
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    el.textContent = "0.0";
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, delay, end]);
  return <span ref={ref} className={s.num} aria-label={`${value} out of 10`}>{value.toFixed(1)}</span>;
}

// ── Music ────────────────────────────────────────────────────────────────────
function useWinnerMusic(end: boolean, verdict: Verdict, cfg: DebateConfig, cols: { prop: string[]; opp: string[] }, chars: Record<string, Character>) {
  const done = useRef(false);
  useEffect(() => {
    if (!end || done.current) return;
    done.current = true;
    const side = verdict.strongerCase;
    if (cfg.format === "panel" || (side !== "prop" && side !== "opp")) {
      audio.setMusic(ARENA.url, { label: ARENA.label, crossfadeMs: 2000 });
      return;
    }
    const ids = cols[side];
    void Promise.all(ids.map((id) => client.characters.song(id).catch(() => null as ThemeSong | null))).then((songs) => {
      const cast: MusicCast[] = ids.map((id, i) => {
        const c = chars[id];
        const song = songs[i];
        return {
          characterId: id,
          name: c?.profile.name ?? id,
          side,
          theme: song && song.status === "ready" && song.url ? { url: song.url, label: `${c?.profile.name.split(" ")[0] ?? "Winner"}'s Theme`, characterId: id } : null,
        };
      });
      const theme = verdictWinnerTheme(cast, verdict);
      audio.setMusic(theme?.url ?? ARENA.url, { label: theme?.label ?? ARENA.label, crossfadeMs: 2000 });
    });
  }, [end]); // eslint-disable-line react-hooks/exhaustive-deps
}

// ── You decide (AC3) ─────────────────────────────────────────────────────────
function YouDecide({ cols, chars, list, sessionId }: { cols: { prop: string[]; opp: string[] }; chars: Record<string, Character>; list: Message[]; sessionId: string }) {
  const [picking, setPicking] = useState<Side | null>(null);
  const closing = (side: Side) => {
    const ids = cols[side];
    const lines = list.filter((m) => m.author.type === "character" && m.kind === "chat" && ids.includes(m.author.characterId ?? ""));
    return lines.slice(-2);
  };
  const pick = async (side: Side) => {
    setPicking(side);
    try {
      await client.debate.pickStrongerCase(sessionId, side);
    } catch (err) {
      reportError(err);
      setPicking(null);
    }
  };
  return (
    <div className={s.decide}>
      <section className={s.banner}>
        <div className={cx(s.bannerTape, s.bannerTie)}>
          <RansomText text="YOUR CALL" size="var(--banner-size)" tone="mixed" slam />
        </div>
        <p className={s.sub}>Read their last words, then pick the side that made the stronger case. One click.</p>
      </section>
      <div className={s.decideGrid}>
        {(["prop", "opp"] as const).map((side) => (
          <section key={side} className={cx(s.decideSide, s[`decide_${side}`])}>
            <div className={s.decideCast}>
              {cols[side].map((cid) => {
                const c = chars[cid];
                return c ? <PortraitCard key={cid} character={c} emotion="neutral" size="thumb" width={84} /> : null;
              })}
            </div>
            <ul className={s.quotes}>
              {closing(side).map((m) => (
                <li key={m.id}>
                  <b>{chars[m.author.characterId ?? ""]?.profile.name.split(" ")[0]}</b> {trim(m.content, 220)}
                </li>
              ))}
              {closing(side).length === 0 && <li className={s.muted}>No closing statement recorded.</li>}
            </ul>
            <button type="button" className={cx(s.pick, s[`pick_${side}`])} disabled={!!picking} onClick={() => void pick(side)}>
              <span className={s.pickKicker}>Stronger case</span>
              <span className={s.pickSide}>{picking === side ? "…" : SIDE_NAME[side]}</span>
            </button>
          </section>
        ))}
      </div>
    </div>
  );
}

const trim = (t: string, n: number) => {
  const plain = t.replace(/[*_#>`]/g, "");
  return plain.length > n ? `${plain.slice(0, n - 1)}…` : plain;
};

// ── Actions dock (88) ────────────────────────────────────────────────────────
function Actions({ sessionId, worldId, cfg, cast, verdict, chars }: { sessionId: string; worldId: string; cfg: DebateConfig; cast: string[]; verdict: Verdict | null; chars: Record<string, Character> }) {
  const [busy, setBusy] = useState<string | null>(null);
  const exportMd = async () => {
    const md = await run(() => client.sessions.export(sessionId));
    if (!md) return;
    const url = URL.createObjectURL(new Blob([md], { type: "text/markdown" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${slug(cfg.motion)}.md`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    toast({ variant: "success", text: "Transcript exported as Markdown." });
  };
  const rematch = async () => {
    setBusy("rematch");
    const sides = Object.fromEntries([...(cfg.sides?.prop ?? []).map((id) => [id, "prop"]), ...(cfg.sides?.opp ?? []).map((id) => [id, "opp"])]) as Record<string, Side>;
    const snap = await run(() => client.sessions.create({ worldId, mode: "debate", characterIds: cast, config: { ...cfg }, sides, continuedFrom: undefined }));
    setBusy(null);
    if (snap) navigate({ name: "session", worldId, sessionId: snap.session.id }, { transition: "slash" });
  };
  const asGroup = async () => {
    setBusy("group");
    const summary = verdict
      ? `Picking up from the debate "${cfg.motion}". ${verdict.summary.map((x) => `${x.subjectId in SIDE_NAME ? SIDE_NAME[x.subjectId as Side] : chars[x.subjectId]?.profile.name ?? x.subjectId}: ${x.points.join(" ")}`).join(" ")}${verdict.keyDisagreement ? ` Key disagreement: ${verdict.keyDisagreement}` : ""}`
      : `Picking up from the debate "${cfg.motion}".`;
    const snap = await run(() => client.sessions.create({ worldId, mode: "group", characterIds: cast, continuedFrom: sessionId, seedSummary: summary, title: `After: ${cfg.motion.slice(0, 60)}` }));
    setBusy(null);
    if (snap) navigate({ name: "session", worldId, sessionId: snap.session.id }, { transition: "slash" });
  };
  useShortcut("e", () => void exportMd());
  return (
    <footer className={s.actions}>
      <Button variant="ghost" onClick={() => void exportMd()}>Export Markdown</Button>
      <Button variant="secondary" disabled={!!busy} onClick={() => void rematch()}>{busy === "rematch" ? "Setting up…" : "Rematch"}</Button>
      <Button variant="secondary" onClick={() => navigate({ name: "hub", worldId, tab: "sessions" })}>Back to Hub</Button>
      <Button size="lg" disabled={!!busy} onClick={() => void asGroup()}>{busy === "group" ? "Gathering…" : "Continue as group chat ▸"}</Button>
    </footer>
  );
}

const slug = (t: string) => t.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "debate";
