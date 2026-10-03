// O11 Mention picker (UXA §2.3): ≤ 5 rows above the caret with head-crop, name and state.
// The Composer keeps focus and drives ↑↓ / Tab / Enter through the mention bus; Esc closes only the picker (R4).
import { useStore } from "zustand";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { useEnergy } from "../../client/hooks";
import { PortraitCard } from "../../character/PortraitCard";
import { audio } from "../../audio/engine";
import { entities } from "../../stores/entities";
import { sessionStore, slotKey } from "../../stores/session";
import { cx } from "../../ui/cx";
import { mentionBus } from "./mentions";
import s from "./Pickers.module.css";

function Row({ id, active, muted, onPick, onHover }: { id: string; active: boolean; muted: boolean; onPick: () => void; onHover: () => void }) {
  const c = useStore(entities, (st) => st.chars[id]);
  const e = useEnergy(id);
  if (!c) return null;
  const asleep = e?.state === "exhausted";
  const state = muted ? "Muted" : asleep ? `Asleep · ⚡${Math.floor(e?.current ?? 0)} · Top up` : e?.state === "tired" ? `Tired · ⚡${Math.floor(e.current)}` : c.profile.role;
  return (
    <li role="option" aria-selected={active} className={cx(s.mRow, active && s.mActive, (asleep || muted) && s.mDim)} onMouseDown={(ev) => { ev.preventDefault(); onPick(); }} onMouseEnter={onHover}>
      <PortraitCard character={c} emotion="neutral" size="head" width={36} energyState={e?.state} parallax={false} />
      <span className={s.mText}>
        <span className={s.mName}>{c.profile.name}</span>
        <span className={s.mState}>{state}</span>
      </span>
    </li>
  );
}

export function MentionPicker({ sessionId, query, onPick }: OverlayComponentProps<"O11">) {
  const { items, active } = useStore(mentionBus);
  const muted = useStore(sessionStore, (st) => {
    const p = st.slots[slotKey(sessionId, false)]?.runtime?.session.participants ?? [];
    return p.filter((x) => x.mutedByUser).map((x) => x.characterId).join(",");
  });
  if (!items.length) return null;
  return (
    <div className={s.mention} role="dialog" aria-label={`Mention a character${query ? ` matching ${query}` : ""}`}>
      <div className={s.mHead}>@ Mention</div>
      <ul role="listbox" className={s.mList}>
        {items.map((it, i) => (
          <Row
            key={it.id}
            id={it.id}
            active={i === active}
            muted={muted.split(",").includes(it.id)}
            onPick={() => onPick(it.id)}
            onHover={() => {
              if (i !== mentionBus.getState().active) {
                mentionBus.setState({ active: i });
                audio.playSfx("ui_hover");
              }
            }}
          />
        ))}
      </ul>
      <div className={s.mFoot}>↑↓ choose · Tab/Enter insert · Esc close</div>
    </div>
  );
}
