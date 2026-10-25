// Speaker cut-in (doc 04 §5): an 18 %-vh strip with an eyes crop + name on a speaker change.
// 300 ms in / 500 ms hold / 200 ms out; never blocks input (pointer-events: none); Display pref `speakerCutIns`.
// Multi-character sessions only (a 1:1 has one speaker). Reduced motion → a short fade.
import { useEffect, useRef, useState, type CSSProperties } from "react";
import type { Character, Emotion } from "../../contract/types";
import { audio } from "../../audio/engine";
import { useMotionPrefs } from "../../motion/prefs";
import { usePrefs } from "../../stores/prefs";
import { PaletteScope } from "../../theme/PaletteScope";
import { cx } from "../../ui/cx";
import { firstName } from "./sessionContext";
import s from "./SpeakerCutIn.module.css";

export const CUTIN_MS = { in: 300, hold: 500, out: 200 } as const;

interface Shot { key: string; char: Character; emotion: Emotion; side?: "prop" | "opp" | null }

export function SpeakerCutIn({ speaker, emotion, side, messageId, suppress }: {
  speaker: Character | undefined;
  emotion: Emotion;
  side?: "prop" | "opp" | null;
  /** The streaming message: a new id from a different speaker triggers the strip. */
  messageId: string | undefined;
  /** Skip (e.g. right after a replay seek). */
  suppress?: boolean;
}) {
  const enabled = usePrefs((p) => p.display.speakerCutIns);
  const { reduced } = useMotionPrefs();
  const [shot, setShot] = useState<Shot | null>(null);
  const lastSpeaker = useRef<string | null>(null);
  const lastMsg = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (!messageId || messageId === lastMsg.current) return;
    lastMsg.current = messageId;
    if (!speaker || speaker.id === lastSpeaker.current) return;
    const first = lastSpeaker.current === null;
    lastSpeaker.current = speaker.id;
    if (!enabled || suppress || first) return;
    setShot({ key: messageId, char: speaker, emotion, side });
    audio.playSfx("ui_cutin");
    // The emotion is fixed at the moment of the cut (no flicker while it streams).
  }, [messageId, speaker, enabled, suppress, emotion, side]);

  useEffect(() => {
    if (!shot) return;
    const total = reduced ? 900 : CUTIN_MS.in + CUTIN_MS.hold + CUTIN_MS.out;
    const t = setTimeout(() => setShot(null), total);
    return () => clearTimeout(t);
  }, [shot, reduced]);

  if (!shot) return null;
  const c = shot.char;
  const url = c.emotions[shot.emotion]?.url ?? c.emotions.neutral?.url;
  return (
    <PaletteScope paletteId={c.paletteId} className={cx(s.cutin, reduced && s.reduced)} key={shot.key}>
      <div className={s.band} aria-hidden="true" style={{ "--in": `${CUTIN_MS.in}ms`, "--hold": `${CUTIN_MS.hold}ms`, "--out": `${CUTIN_MS.out}ms` } as CSSProperties}>
        <div className={s.eyes}>{url && <img src={url} alt="" draggable={false} />}</div>
        <div className={s.name}>
          {shot.side && <span className={s.side}>{shot.side === "prop" ? "Proposition" : "Opposition"}</span>}
          <span className={s.big}>{firstName(c.profile.name)}</span>
          <span className={s.role}>{c.profile.role}</span>
        </div>
        <div className={s.speed} />
      </div>
    </PaletteScope>
  );
}
