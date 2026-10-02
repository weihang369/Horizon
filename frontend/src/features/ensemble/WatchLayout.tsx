// S12 Watch layout (R14) — Builder D. Theatre, distinct from Group: a proscenium ROW of bottom-anchored portraits
// (46 % vh) under a subtitle-style script (760/680, last ~8 lines, top fade mask; full log via L / O10).
// The speaker steps into a palette spotlight. Episode end (turn limit) opens O17 live; Replay shows a curtain card.
import { useEffect, useMemo, useRef } from "react";
import type { CSSProperties } from "react";
import type { WatchConfig, WatchState } from "../../contract/types";
import { openOverlay } from "../../app/layers";
import { EnergyBar, NamePlate } from "../../character";
import { PaletteScope } from "../../theme";
import { RansomText, Tape, cx } from "../../ui";
import { SessionLog } from "../session/SessionLog";
import type { LayoutProps } from "../session/registry";
import { StageCard } from "./StageCard";
import { activeSpeakerId, lastSpeakerId, latestReactions, useBoundary, useCharMap } from "./shared";
import s from "./WatchLayout.module.css";

export function WatchLayout({ rt, replay }: LayoutProps) {
  const chars = useCharMap();
  const session = rt.session!;
  const cfg = session.config as WatchConfig | null;
  const st = session.state as WatchState | null;
  const status = rt.watch?.status ?? st?.status ?? "paused";
  const ended = status === "ended";
  const active = activeSpeakerId(rt);
  const lit = active ?? lastSpeakerId(rt.list);
  const reactions = useMemo(() => latestReactions(rt.list), [rt.list]);
  const n = rt.participants.length;
  const seq = rt.runtime?.lastSeq ?? 0;
  const turns = rt.watch?.turnsTaken ?? st?.turnsTaken ?? 0;
  const limit = rt.watch?.turnLimit ?? st?.turnLimit ?? cfg?.maxTurns ?? 0;

  // Episode end: the turn limit was reached during this viewing (never on open, never on a seek).
  useBoundary(ended ? "ended" : "running", seq, (next) => {
    if (next === "ended" && !replay) openOverlay("O17", { sessionId: session.id });
  });
  // Opened on an already-finished live episode: offer the card once.
  const offered = useRef(false);
  useEffect(() => {
    if (replay || offered.current || !rt.session) return;
    offered.current = true;
    if (ended && session.status !== "ended") openOverlay("O17", { sessionId: session.id });
  }, [replay, ended, rt.session, session.id, session.status]);

  const onAir = status === "playing" && !rt.paused;

  return (
    <div className={s.root} data-layout="watch" style={{ "--n": n } as CSSProperties}>
      <div className={s.lights} aria-hidden="true">
        {rt.participants.map((p, i) => (
          <PaletteScope
            key={p.characterId}
            paletteId={chars[p.characterId]?.paletteId}
            className={cx(s.spot, lit === p.characterId && s.spotOn, active === p.characterId && s.spotHot)}
            style={{ "--x": `${((i + 0.5) / Math.max(n, 1)) * 100}%` } as CSSProperties}
          />
        ))}
      </div>
      <div className={s.curtainL} aria-hidden="true" />
      <div className={s.curtainR} aria-hidden="true" />

      <header className={s.marquee}>
        <span className={cx(s.onAir, onAir && s.onAirLive)}>
          <i aria-hidden="true" />
          {ended ? "End of episode" : onAir ? "On air" : rt.paused || status === "paused" ? "Paused" : "Standby"}
        </span>
        {cfg?.premise && (
          <p className={s.premise}>
            <span className={s.sceneTag}>Scene</span>
            {cfg.premise}
          </p>
        )}
        <span className={s.counter}>
          Turn <b>{turns}</b>/{limit}
        </span>
      </header>

      <div className={s.script}>
        <SessionLog rt={rt} variant="script" className={s.log} emptyText={rt.status === "loading" ? "" : "The scene is about to begin."} />
      </div>

      <div className={s.row} data-stage-root="" aria-label="Cast">
        <div className={s.floor} aria-hidden="true" />
        {rt.participants.map((p, i) => {
          const c = chars[p.characterId];
          if (!c) return null;
          const speaking = active === p.characterId;
          const energy = rt.energyById[p.characterId]?.state ?? c.energy.state;
          const next = rt.nextSpeakerId === p.characterId && !speaking && !ended;
          return (
            <div key={p.characterId} className={cx(s.actor, speaking && s.speaking, p.leanIn && s.lean)} style={{ "--i": i } as CSSProperties}>
              {next && <span className={s.cue} aria-hidden="true">Cue</span>}
              <StageCard
                sessionId={session.id}
                character={c}
                emotion={p.displayEmotion}
                size="stage"
                width="var(--actor-w)"
                speaking={speaking}
                listening={!!active && !speaking}
                dimmed={p.mutedByUser}
                energyState={energy}
                reaction={reactions[p.characterId] ?? null}
              />
              <div className={s.foot}>
                <NamePlate character={c} size="sm" subtitle={p.mutedByUser ? "Muted" : energy === "exhausted" ? "Asleep" : null} />
                <EnergyBar characterId={c.id} size="stage" label={c.profile.name} className={s.energy} />
              </div>
            </div>
          );
        })}
      </div>

      {ended && replay && (
        <div className={s.curtainCard} role="status">
          <RansomText text="FIN" size={56} tone="mixed" />
          <Tape tone="ink" size="sm">End of episode · {turns} turns</Tape>
        </div>
      )}
    </div>
  );
}
