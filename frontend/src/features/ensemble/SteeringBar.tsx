// SteeringBar dock (MULTI-07, UXA §2.3) — Builder D. 72 px:
// ❚❚/▶ · Next · Ask… · Interject · Extend round · Skip to closing · End | auto-advance.
// Ask…/Interject open O12 DockExpansions (they hold the queue at the next boundary). Space = pause/resume, → = Next.
import { client } from "../../client";
import type { DebateConfig, DebateState } from "../../contract/types";
import { run } from "../../app/errors";
import { openOverlay } from "../../app/layers";
import { useShortcut } from "../../app/shortcuts";
import { navigate } from "../../router";
import { useUi } from "../../stores/ui";
import { Button, Kbd, NextIcon, PauseIcon, PlayIcon, Toggle, cx } from "../../ui";
import type { DockProps } from "../session/registry";
import s from "./Dock.module.css";

export function SteeringBar({ rt, sessionId, worldId }: DockProps) {
  const session = rt.session;
  const cfg = session?.config as DebateConfig | null;
  const st = session?.state as DebateState | null;
  const phase = rt.phase?.phase ?? st?.phase;
  const ended = session?.status === "ended" || phase === "ended";
  const atVerdict = phase === "verdict";
  const auto = cfg?.autoAdvance ?? true;
  const expansion = useUi((u) => u.dockExpansion);
  const open = expansion?.sessionId === sessionId ? expansion.kind : null;
  const beforeClosing = phase === "setup" || phase === "opening" || phase === "rebuttal";
  const busy = !!rt.streamingId || !!rt.thinkingId;

  const togglePause = () => void run(() => (rt.paused ? client.debate.resume(sessionId) : client.debate.pause(sessionId)));
  const next = () => void run(() => client.debate.next(sessionId));
  const end = () => {
    if (atVerdict) navigate({ name: "verdict", worldId, sessionId });
    else if (beforeClosing) openOverlay("O26", { sessionId });
    else void run(() => client.debate.endDebate(sessionId, true)).then(() => navigate({ name: "verdict", worldId, sessionId }));
  };

  useShortcut("space", togglePause, { when: () => !ended });
  useShortcut("arrowright", next, { when: () => !ended && !auto && !busy });

  return (
    <div className={s.dock} role="toolbar" aria-label="Debate steering">
      <div className={s.group}>
        <Button
          size="sm"
          variant={rt.paused ? "primary" : "secondary"}
          disabled={ended}
          onClick={togglePause}
          icon={rt.paused ? <PlayIcon /> : <PauseIcon />}
          aria-label={rt.paused ? "Resume (Space)" : "Pause (Space)"}
          className={s.square}
        />
        <Button size="sm" variant="secondary" disabled={ended || auto || busy} onClick={next} iconRight={<NextIcon />} title={auto ? "Turn auto-advance off to step manually" : "Next turn (→)"}>
          Next
        </Button>
        <span className={s.divider} aria-hidden="true" />
        <Button
          size="sm"
          variant={open === "ask" ? "primary" : "secondary"}
          disabled={ended || atVerdict}
          aria-expanded={open === "ask"}
          onClick={() => openOverlay("O12", { sessionId, kind: "ask" })}
        >
          Ask…
        </Button>
        <Button
          size="sm"
          variant={open === "interject" ? "primary" : "secondary"}
          disabled={ended || atVerdict}
          aria-expanded={open === "interject"}
          onClick={() => openOverlay("O12", { sessionId, kind: "interject" })}
        >
          Interject
        </Button>
        <Button size="sm" variant="ghost" disabled={ended || atVerdict} onClick={() => void run(() => client.debate.extendRound(sessionId))}>
          Extend round
        </Button>
        <Button size="sm" variant="ghost" disabled={ended || !beforeClosing} onClick={() => void run(() => client.debate.skipToClosing(sessionId))}>
          Skip to closing
        </Button>
        <Button size="sm" variant={atVerdict || ended ? "primary" : "danger"} onClick={end} disabled={ended && !st?.verdict}>
          {atVerdict || (ended && st?.verdict) ? "Verdict ▸" : "End"}
        </Button>
      </div>
      <div className={cx(s.group, s.right)}>
        <span className={s.hint}>
          <Kbd>Space</Kbd> pause{!auto && <> · <Kbd>→</Kbd> next</>}
        </span>
        <Toggle
          checked={auto}
          disabled={ended}
          label="Auto-advance"
          onChange={(on) => void run(() => client.debate.setAutoAdvance(sessionId, on))}
        />
      </div>
    </div>
  );
}
