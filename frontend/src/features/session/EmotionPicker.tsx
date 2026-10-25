// O07 Emotion picker + the MANUAL face strip (CHAT-04, D-50). Seven faces, Alt+1…7 (works while typing).
// It changes the face only (D-07): `chat.setEmotion` emits an `emotion` event without messageId (D-51).
// D-56: neutral is silent in sessions; its kit sound is the picker's hover tick.
import { useStore } from "zustand";
import { client } from "../../client";
import { sessionStore, slotKey } from "../../stores/session";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { run } from "../../app/errors";
import { audio } from "../../audio/engine";
import { emotionMeta, EMOTION_ORDER } from "../../character/emotionMeta";
import type { Emotion } from "../../contract/types";
import { Kbd } from "../../ui/Kbd";
import { cx } from "../../ui/cx";
import s from "./Pickers.module.css";

export function setFace(sessionId: string, characterId: string, emotion: Emotion): void {
  void run(() => client.chat.setEmotion(sessionId, characterId, emotion));
}

export interface EmotionStripProps {
  sessionId: string;
  characterId: string;
  current: Emotion;
  /** Some emotions may have no art yet (Lean mode): still selectable, shown with a dot (EMO-06). */
  available?: Partial<Record<Emotion, boolean>>;
  orientation?: "vertical" | "grid";
  onPicked?: () => void;
  className?: string;
}

/** The 7×44 px MANUAL strip on the S07 seam (UXA §2.2), also the body of O07. */
export function EmotionStrip({ sessionId, characterId, current, available, orientation = "vertical", onPicked, className }: EmotionStripProps) {
  return (
    <div role="radiogroup" aria-label="Set face (Alt+1…7)" className={cx(s.strip, s[orientation], className)}>
      {EMOTION_ORDER.map((e) => {
        const m = emotionMeta[e];
        const on = e === current;
        return (
          <button
            key={e}
            type="button"
            role="radio"
            aria-checked={on}
            className={cx(s.face, on && s.faceOn)}
            title={`${m.label} (Alt+${m.hotkey})`}
            onMouseEnter={() => audio.playSfx("emo_neutral")}
            onClick={() => {
              if (!on) setFace(sessionId, characterId, e);
              onPicked?.();
            }}
          >
            <span className={s.faceIcon} aria-hidden="true">{m.icon}</span>
            <span className={s.faceLabel}>{m.label}</span>
            <span className={s.faceKey} aria-hidden="true">{m.hotkey}</span>
            {available && available[e] === false && <span className={s.faceMissing} aria-label="no art yet" />}
          </button>
        );
      })}
    </div>
  );
}

export function EmotionPicker({ sessionId, characterId, close }: OverlayComponentProps<"O07">) {
  const current = useStore(sessionStore, (st) => st.slots[slotKey(sessionId, false)]?.runtime?.displayEmotion[characterId] ?? "neutral");
  return (
    <div className={s.emoPop} role="dialog" aria-label="Emotion picker">
      <div className={s.mHead}>Manual face <span className={s.hintKeys}><Kbd>Alt</Kbd>+<Kbd>1…7</Kbd></span></div>
      <EmotionStrip sessionId={sessionId} characterId={characterId} current={current} orientation="grid" onPicked={close} />
    </div>
  );
}
