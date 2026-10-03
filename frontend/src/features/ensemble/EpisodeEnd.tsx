// O17 Episode end (MULTI-10 AC2) — Builder D. A ceremony-kind card (the entry is skippable, R6): the curtain
// drops on the turn limit and offers Continue +10 · Summarise · Back. Esc dismisses it (the transport keeps a
// way back via "Episode end ▸").
import { useEffect, useState } from "react";
import { client } from "../../client";
import type { WatchState } from "../../contract/types";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { run } from "../../app/errors";
import { useShortcut } from "../../app/shortcuts";
import { audio } from "../../audio/engine";
import { playCeremony, useCeremony, useMotionPrefs } from "../../motion";
import { navigate } from "../../router";
import { Button, RansomText, cx } from "../../ui";
import { useSlot } from "./shared";
import s from "./Overlays.module.css";

let n = 0;

export function EpisodeEnd({ sessionId, close }: OverlayComponentProps<"O17">) {
  const slot = useSlot(sessionId);
  const session = slot?.runtime?.session;
  const st = session?.state as WatchState | null;
  const watch = slot?.runtime?.watch;
  const turns = watch?.turnsTaken ?? st?.turnsTaken ?? 0;
  const limit = watch?.turnLimit ?? st?.turnLimit ?? 0;
  const [id] = useState(() => `O17:${++n}`);
  const { active, skipped } = useCeremony(id);
  const { reduced } = useMotionPrefs();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let h: { skip(): void } | null = null;
    const t = window.setTimeout(() => {
      h = playCeremony(id, { durationMs: 900 });
      audio.playSfx("ui_whoosh");
    }, 0);
    return () => {
      clearTimeout(t);
      h?.skip();
    };
  }, [id]);

  useShortcut("escape", close);

  const extend = async () => {
    setBusy(true);
    await run(() => client.watch.extendWatch(sessionId, 10));
    setBusy(false);
    close();
  };
  const summarise = async () => {
    setBusy(true);
    await run(() => client.watch.summarise(sessionId));
    setBusy(false);
    close();
  };

  return (
    <div className={s.episodeScrim}>
      <section
        className={cx(s.episode, (active && !skipped && !reduced) && s.episodeIn)}
        role="dialog"
        aria-modal="false"
        aria-labelledby={`${id}-t`}
      >
        <div className={s.epCurtain} aria-hidden="true" />
        <span className={s.epKicker}>{limit ? `Turn ${turns} / ${limit}` : "Episode"}</span>
        <h2 id={`${id}-t`} className={s.epTitle}>
          <RansomText text="END OF EPISODE" size={54} tone="mixed" />
        </h2>
        <p className={s.epBody}>The scene stops here. Keep it going, get the gist, or head back.</p>
        <div className={s.epActions}>
          <Button disabled={busy} onClick={() => void extend()} autoFocus>Continue +10</Button>
          <Button variant="secondary" disabled={busy} onClick={() => void summarise()}>Summarise</Button>
          <Button
            variant="ghost"
            onClick={() => {
              close();
              if (session) navigate({ name: "hub", worldId: session.worldId });
            }}
          >
            ◂ Back
          </Button>
        </div>
      </section>
    </div>
  );
}
