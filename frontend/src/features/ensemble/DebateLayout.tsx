// S10 Debate layout (Builder D): motion banner · timeline rail with NEXT ▸ cue · PROP column | log | OPP column (R14).
// Scoped palettes (R9/D-54): chrome stays house orange; each palette lives only in its character's frame, plate and
// energy bar; the active speaker tints the stage band. Phase changes fire O16 (VS splash, Round banner) via the
// conductor, never during a Replay seek. Auto host = a HOST tape under the banner, no portrait (MULTI-07 AC5).
import { useEffect, useMemo, useRef } from "react";
import type { CSSProperties } from "react";
import type { DebateConfig, DebateState, Message } from "../../contract/types";
import { openOverlay } from "../../app/layers";
import { navigate } from "../../router";
import { useUi } from "../../stores/ui";
import { EnergyBar, NamePlate, PortraitCard } from "../../character";
import { PaletteScope } from "../../theme";
import { Button, RansomText, Tape, cx } from "../../ui";
import { SessionLog } from "../session/SessionLog";
import type { LayoutProps } from "../session/registry";
import { StageCard } from "./StageCard";
import {
  activeSpeakerId, debateColumns, firstName, frontFirst, latestReactions, railSteps, recentSpeakerIn, roundBannerLabel,
  useBoundary, useCharMap,
} from "./shared";
import s from "./DebateLayout.module.css";

type ColSide = "prop" | "opp";

export function DebateLayout({ rt, replay, route }: LayoutProps) {
  const chars = useCharMap();
  const session = rt.session!;
  const cfg = session.config as DebateConfig | null;
  const st = session.state as DebateState | null;
  const panel = cfg?.format === "panel";
  const cols = useMemo(() => debateColumns(rt.participants, cfg), [rt.participants, cfg]);
  const active = activeSpeakerId(rt);
  const next = rt.nextSpeakerId;
  const reactions = useMemo(() => latestReactions(rt.list), [rt.list]);
  const byId = useMemo(() => Object.fromEntries(rt.participants.map((p) => [p.characterId, p])), [rt.participants]);
  const expansion = useUi((u) => u.dockExpansion);
  const held = !!expansion && expansion.sessionId === session.id && (expansion.kind === "ask" || expansion.kind === "interject");
  const phase = rt.phase ?? (st ? { phase: st.phase, round: st.round, iteration: st.iteration } : null);
  const seq = rt.runtime?.lastSeq ?? 0;
  const verdictReady = !!st?.verdict && (phase?.phase === "verdict" || phase?.phase === "ended");

  // ── Ceremonies (O16): VS on the first round, a Round banner on every later boundary ──
  const phaseKey = phase && phase.phase !== "setup" && phase.phase !== "ended" ? `${phase.phase}:${phase.round}:${phase.iteration}` : null;
  useBoundary(phaseKey, seq, (_next, prev) => {
    if (!phase) return;
    const first = phase.phase === (cfg?.phases[0] ?? "opening") && phase.round <= 1 && phase.iteration <= 1 && !prev;
    openOverlay("O16", { sessionId: session.id, kind: first ? "vs" : "round", label: roundBannerLabel(phase) });
  });

  // Live: the verdict lands → S11 (Replay keeps the CTA so the viewer stays in control).
  const wentToVerdict = useRef(false);
  useEffect(() => {
    if (replay || !verdictReady || wentToVerdict.current || session.status !== "ended") return;
    wentToVerdict.current = true;
    const t = window.setTimeout(() => navigate({ name: "verdict", worldId: route.worldId, sessionId: session.id }), 1400);
    return () => window.clearTimeout(t);
  }, [replay, verdictReady, session.status, session.id, route.worldId]);

  // Stage band: the active (or last) speaker's palette, crossfaded by opacity (palette vars never interpolate, R10).
  const bandId = active ?? recentSpeakerIn(rt.participants.map((p) => p.characterId), rt.list);
  const hostLine = useMemo(() => (cfg?.moderator === "auto_host" ? lastHost(rt.list) : undefined), [cfg?.moderator, rt.list]);
  const nextChar = next && !verdictReady && phase?.phase !== "verdict" ? chars[next] : undefined;
  const steps = railSteps(cfg?.phases ?? ["opening", "rebuttal", "closing"], phase?.phase);
  const motion = cfg?.motion ?? session.title;

  const column = (side: ColSide) => {
    const ids = cols[side];
    const focus = (active && ids.includes(active) ? active : undefined)
      ?? (next && ids.includes(next) ? next : undefined)
      ?? recentSpeakerIn(ids, rt.list);
    const order = frontFirst(ids, focus);
    return (
      <section
        className={cx(s.column, s[side])}
        aria-label={panel ? `Panel ${side === "prop" ? "left" : "right"}` : side === "prop" ? "Proposition" : "Opposition"}
        data-stage-root=""
      >
        <div className={s.sideHead}>
          {panel
            ? <Tape tone="ink" size="sm">Panel</Tape>
            : <Tape tone={side} size="md" rotate={side === "prop" ? -3 : 3}>{side === "prop" ? "Proposition" : "Opposition"}</Tape>}
          <span className={s.count}>{ids.length}</span>
        </div>
        <div className={s.slots}>
          {order.map((cid, rank) => {
            const c = chars[cid];
            const p = byId[cid];
            if (!c || !p) return null;
            const speaking = active === cid;
            const energy = rt.energyById[cid]?.state ?? c.energy.state;
            const front = rank === 0;
            return (
              <div
                key={cid}
                className={cx(s.slot, speaking && s.slotSpeaking, p.leanIn && s.slotLean)}
                data-rank={Math.min(rank, 2)}
                style={{ zIndex: 10 - rank } as CSSProperties}
              >
                <NamePlate character={c} size="sm" subtitle={null} className={s.backTag} />
                {next === cid && !speaking && <span className={s.upNext} aria-hidden="true">Up next</span>}
                <StageCard
                  sessionId={session.id}
                  character={c}
                  emotion={p.displayEmotion}
                  size="stage"
                  width="var(--card-w)"
                  speaking={speaking}
                  listening={!!active && !speaking}
                  dimmed={p.mutedByUser}
                  energyState={energy}
                  reaction={reactions[cid] ?? null}
                />
                <div className={s.foot} aria-hidden={!front}>
                  <NamePlate character={c} size="md" subtitle={plateSub(c.profile.role, p.side, energy)} />
                  <EnergyBar characterId={cid} size="stage" label={c.profile.name} className={s.energy} />
                </div>
              </div>
            );
          })}
        </div>
      </section>
    );
  };

  return (
    <div className={s.root} data-layout="debate">
      <div className={s.bands} aria-hidden="true">
        {rt.participants.map((p) => {
          const c = chars[p.characterId];
          return (
            <PaletteScope
              key={p.characterId}
              paletteId={c?.paletteId}
              className={cx(s.band, bandId === p.characterId && s.bandOn, active === p.characterId && s.bandHot)}
            />
          );
        })}
        <div className={s.halftone} />
      </div>

      <header className={s.banner}>
        <div className={s.bannerTape}>
          <RansomText text="MOTION" size={22} tone="mixed" className={s.motionTag} />
          <h1 className={cx(s.motion, motion.length > 72 && s.motionLong)}>{motion}</h1>
        </div>
      </header>

      <nav className={s.rail} aria-label="Debate timeline">
        <ol className={s.steps}>
          {steps.map((x, i) => (
            <li key={x.phase} className={s.step} data-state={x.state}>
              {i > 0 && <span className={s.wire} aria-hidden="true" />}
              <span className={s.dot} aria-hidden="true" />
              <span className={s.stepLabel}>
                {x.label}
                {x.state === "current" && phase && phase.iteration > 1 ? ` ×${phase.iteration}` : ""}
              </span>
              {x.state === "current" && <span className="sr-only"> (current)</span>}
            </li>
          ))}
        </ol>
        <div className={s.railRight}>
          {phase && phase.phase !== "setup" && phase.phase !== "ended" && (
            <span className={s.roundNo}>Round {phase.round}</span>
          )}
          <div className={cx(s.nextChip, held && s.nextHeld)} aria-live="polite" aria-atomic="true">
            <span className={s.nextLabel}>{held ? "Held" : next && next === active ? "Now" : "Next"} ▸</span>
            {nextChar && !held ? (
              <>
                <PortraitCard character={nextChar} emotion={byId[nextChar.id]?.displayEmotion ?? "neutral"} size="head" width={26} />
                <span className={s.nextName}>{firstName(nextChar)}</span>
              </>
            ) : (
              <span className={s.nextName}>{held ? "Moderator" : verdictReady ? "Verdict" : "—"}</span>
            )}
          </div>
        </div>
      </nav>

      {hostLine && (
        <div className={s.host} role="status">
          <Tape tone="brand" size="sm">Host</Tape>
          <p className={s.hostText}>{hostLine.content}</p>
        </div>
      )}

      <div className={cx(s.arena, hostLine && s.arenaHost)}>
        {column("prop")}
        <div className={s.logPanel}>
          <SessionLog rt={rt} className={s.log} />
          {verdictReady && (
            <div className={s.verdictCta}>
              <Tape tone="ink" size="sm">The arbiter has spoken</Tape>
              <Button size="lg" onClick={() => navigate({ name: "verdict", worldId: route.worldId, sessionId: session.id })}>
                See the verdict ▸
              </Button>
            </div>
          )}
        </div>
        {column("opp")}
      </div>
    </div>
  );
}

function plateSub(role: string, side: "prop" | "opp" | null | undefined, energy: string): string {
  if (energy === "exhausted") return "Asleep · recharging";
  const tag = side === "prop" ? "PROP" : side === "opp" ? "OPP" : "PANEL";
  const short = role.length > 26 ? `${role.slice(0, 25)}…` : role;
  return `${tag} · ${short}`;
}

function lastHost(list: Message[]): Message | undefined {
  for (let i = list.length - 1; i >= 0; i--) if (list[i].author.type === "host") return list[i];
  return undefined;
}
