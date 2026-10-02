// DemoDock (R15, APP-09 AC5/AC6): "Recorded · ▶ Replay · Continue live (needs key)".
// A seed recording stays replay-only even with a key; Continue live forks it (whole recording, R16).
// A user's own session in demo mode (key removed) gets the Composer, whose Send asks for a key.
import { navigate } from "../../router";
import { Tape } from "../../ui/Tape";
import { KeyIcon, PlayIcon, ChevronRightIcon } from "../../ui/icons";
import { Composer } from "./Composer";
import { continueLive } from "./ReplayTransport";
import { useSessionCtx } from "./sessionContext";
import type { DockProps } from "./registry";
import s from "./DemoDock.module.css";

export function DemoDock(props: DockProps) {
  const { rt, sessionId, worldId } = props;
  const ctx = useSessionCtx();
  const seed = rt.session?.isSeed ?? true;
  const demo = ctx?.demo ?? true;
  if (!seed) return <Composer {...props} variant={rt.session?.mode === "one_on_one" ? "inline" : "dock"} />;
  return (
    <div className={s.dock} role="group" aria-label="Recorded session">
      <div className={s.fake} aria-hidden="true">
        <span className={s.fakeText}>This conversation is a recording.</span>
      </div>
      <div className={s.copy}>
        <Tape tone="paper" size="sm">● Recorded</Tape>
        <span className={s.note}>{demo ? "Live replies need your OpenRouter key." : "Recordings stay as shipped. Continue live makes your own copy."}</span>
      </div>
      <div className={s.actions}>
        <button type="button" className={s.btn} onClick={() => navigate({ name: "session", worldId, sessionId, replay: true })}>
          <span className={s.shape} aria-hidden="true" />
          <span className={s.content}><PlayIcon width={16} height={16} />Replay</span>
        </button>
        <button
          type="button"
          className={`${s.btn} ${s.primary}`}
          data-key-locked={demo || undefined}
          onClick={() => void continueLive(sessionId, worldId, rt.session?.title ?? "", undefined, demo)}
          aria-label={`Continue live${demo ? " (needs API key)" : ""}`}
        >
          <span className={s.shape} aria-hidden="true" />
          <span className={s.content}>{demo && <KeyIcon width={14} height={14} />}Continue live<ChevronRightIcon width={16} height={16} /></span>
        </button>
      </div>
    </div>
  );
}
