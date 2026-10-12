// Insight's Emotion section body (INS-01; turn-plan-emotion D15): a kept face shows no band (rules in emotionView.ts).
// Display only. Owner: AI.
import { emotionMeta } from "../../character/emotionMeta";
import { probBand } from "../../domain/format";
import { ProbBar } from "../../ui/Data";
import { cx } from "../../ui/cx";
import { emotionView, type TraceEmotion } from "./emotionView";
import s from "./InsightDrawer.module.css";

const r2 = (p: number) => Math.round(p * 100) / 100;

export function EmotionBody({ emotion: e, armed, manual }: { emotion: TraceEmotion; armed: boolean; manual: boolean }) {
  const { cands, kept } = emotionView(e);
  const band = cands[0] && !kept ? probBand(r2(cands[0].p)) : null;
  return (
    <>
      <p className={s.chosen}><span className={s.chosenIcon} aria-hidden="true">{emotionMeta[e.chosen].icon}</span>{emotionMeta[e.chosen].label}{band && <span className={cx(s.band, s[`band_${band}`])}>{band}</span>}</p>
      {cands.length > 0 && (
        <div className={s.bars}>
          {cands.map((x) => (
            <ProbBar key={x.label} label={<><span className={s.emoIcon} aria-hidden="true">{emotionMeta[x.label].icon}</span>{emotionMeta[x.label].label}</>} p={armed ? r2(x.p) : 0} color={x.label === e.chosen ? undefined : "var(--paper-300)"} />
          ))}
        </div>
      )}
      {manual && <p className={s.fine}>MANUAL mode: recorded here, not shown on the portrait.</p>}
    </>
  );
}
