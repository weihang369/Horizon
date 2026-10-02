// Watch Transport dock (MULTI-10/11, UXA §2.2 S12) — Builder D. 72 px:
// ❚❚/▶ · Step → · Pace [Slow|Normal|Fast] · ■ | Step in · 🎬 Director's note | episode rail "TURN 6 / 10".
// Pace is Slow/Normal/Fast only (D-50; ×N is Replay's). Space = play/pause, → = Step.
import { client } from "../../client";
import type { WatchConfig, WatchState } from "../../contract/types";
import { run } from "../../app/errors";
import { openOverlay } from "../../app/layers";
import { useShortcut } from "../../app/shortcuts";
import { useUi } from "../../stores/ui";
import { Button, NextIcon, PauseIcon, PlayIcon, Segmented, StopIcon, cx } from "../../ui";
import type { DockProps } from "../session/registry";
import { PACE_OPTIONS } from "./shared";
import s from "./Dock.module.css";

export function Transport({ rt, sessionId }: DockProps) {
  const session = rt.session;
  const cfg = session?.config as WatchConfig | null;
  const st = session?.state as WatchState | null;
  const status = rt.watch?.status ?? st?.status ?? "paused";
  const playing = status === "playing" && !rt.paused;
  const ended = status === "ended" || session?.status === "ended";
  const turns = rt.watch?.turnsTaken ?? st?.turnsTaken ?? 0;
  const limit = rt.watch?.turnLimit ?? st?.turnLimit ?? cfg?.maxTurns ?? 20;
  const pace = String(rt.watch?.paceMs || cfg?.paceMs || 1500);
  const busy = !!rt.streamingId || !!rt.thinkingId;
  const expansion = useUi((u) => u.dockExpansion);
  const open = expansion?.sessionId === sessionId ? expansion.kind : null;
  // After Step in, the scene waits: offer "▶ Resume the scene" (MULTI-11 AC1).
  const lastUser = [...rt.list].reverse().find((m) => m.author.type === "user");
  const waitingAfterStepIn = !playing && !ended && lastUser?.kind === "chat";

  const toggle = () => void run(() => (playing ? client.watch.pause(sessionId) : client.watch.play(sessionId)));
  const step = () => void run(() => client.watch.step(sessionId));
  const stop = () => {
    if (playing) void run(() => client.watch.pause(sessionId));
    openOverlay("O17", { sessionId });
  };

  useShortcut("space", () => (ended ? openOverlay("O17", { sessionId }) : toggle()));
  useShortcut("arrowright", step, { when: () => !ended && !busy });

  return (
    <div className={s.dock} role="toolbar" aria-label="Scene transport">
      <div className={s.group}>
        {waitingAfterStepIn ? (
          <Button size="md" onClick={toggle} icon={<PlayIcon />} className={s.resume}>Resume the scene</Button>
        ) : (
          <Button
            size="md"
            variant={playing ? "secondary" : "primary"}
            disabled={ended}
            onClick={toggle}
            icon={playing ? <PauseIcon /> : <PlayIcon />}
            aria-label={playing ? "Pause (Space)" : "Play (Space)"}
            className={s.square}
          />
        )}
        <Button size="md" variant="secondary" disabled={ended || busy} onClick={step} iconRight={<NextIcon />} title="Step one turn (→)">
          Step
        </Button>
        <Segmented
          label="Pace"
          value={pace}
          options={PACE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
          onChange={(v) => void run(() => client.watch.setPace(sessionId, Number(v) as WatchConfig["paceMs"]))}
          className={s.pace}
        />
        <Button size="md" variant="ghost" onClick={stop} icon={<StopIcon />} aria-label="Stop · end the episode" className={s.square} />
        <span className={s.divider} aria-hidden="true" />
        <Button
          size="md"
          variant={open === "stepin" ? "primary" : "secondary"}
          disabled={ended}
          aria-expanded={open === "stepin"}
          onClick={() => openOverlay("O12", { sessionId, kind: "stepin" })}
        >
          Step in
        </Button>
        <Button
          size="md"
          variant={open === "direction" ? "primary" : "secondary"}
          disabled={ended}
          aria-expanded={open === "direction"}
          onClick={() => openOverlay("O12", { sessionId, kind: "direction" })}
        >
          🎬 Note
        </Button>
      </div>
      <EpisodeRail turns={turns} limit={limit} ended={ended} onEnd={() => openOverlay("O17", { sessionId })} />
    </div>
  );
}

export function EpisodeRail({ turns, limit, ended, onEnd }: { turns: number; limit: number; ended?: boolean; onEnd?: () => void }) {
  const ticks = Math.min(limit, 40);
  return (
    <div className={cx(s.group, s.right, s.episode)}>
      <div className={s.ticks} role="progressbar" aria-label="Episode progress" aria-valuemin={0} aria-valuemax={limit} aria-valuenow={turns}>
        {Array.from({ length: ticks }, (_, i) => (
          <i key={i} data-on={i < Math.round((turns / limit) * ticks) || undefined} />
        ))}
      </div>
      {ended && onEnd ? (
        <button type="button" className={s.turnBtn} onClick={onEnd}>Episode end ▸</button>
      ) : (
        <span className={s.turn}>
          Turn <b>{turns}</b> / {limit}
        </span>
      )}
    </div>
  );
}
