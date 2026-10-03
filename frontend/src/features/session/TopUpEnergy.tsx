// O27 Energy top-up (ENG-05): "Give {name} +500 ⚡ (≈ US$0.05)?" with +500 / +1000. Counts against the daily cap
// (blocked → O21 via reportError). Success plays the recharge (EnergyBar sparks + SFX) and wakes the character.
import { useState } from "react";
import { useStore } from "zustand";
import { client } from "../../client";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { toast } from "../../app/layers";
import { run } from "../../app/errors";
import { useEnergy, useSettings } from "../../client/hooks";
import { audio } from "../../audio/engine";
import { EnergyBar } from "../../character/EnergyBar";
import { PortraitCard } from "../../character/PortraitCard";
import { formatUsd } from "../../domain/format";
import { entities } from "../../stores/entities";
import { PaletteScope } from "../../theme/PaletteScope";
import { Button } from "../../ui/Button";
import { Modal } from "../../ui/Panels";
import { cx } from "../../ui/cx";
import { firstName } from "./sessionContext";
import s from "./TopUpEnergy.module.css";

export function TopUpEnergy({ characterId, close }: OverlayComponentProps<"O27">) {
  const c = useStore(entities, (st) => st.chars[characterId]);
  const settings = useSettings().data;
  const e = useEnergy(characterId);
  const step = settings?.energy.topUpStepPoints ?? 500;
  const usdPer = settings?.energy.usdPerPoint ?? 0.0001;
  const [pts, setPts] = useState(step);
  const [busy, setBusy] = useState(false);
  const name = c ? firstName(c.profile.name) : "them";
  const options = [step, step * 2];
  const cost = pts * usdPer;
  const spent = settings?.spentTodayUsd ?? 0;
  const cap = settings?.budget.dailyCapUsd ?? 1;

  const confirm = async () => {
    setBusy(true);
    const ok = await run(() => client.characters.topUpEnergy(characterId, pts).then(() => true));
    setBusy(false);
    if (!ok) return;
    audio.playSfx("energy_topup");
    toast({ variant: "success", text: `${name} is recharged (+${pts} ⚡).` });
    setTimeout(close, 650);
  };

  return (
    <Modal
      tape="Energy"
      title={<>Give {name} +{pts} ⚡?</>}
      size="sm"
      onClose={close}
      actions={
        <>
          <Button variant="ghost" onClick={close}>Not now</Button>
          <Button onClick={() => void confirm()} disabled={busy} cost={cost} autoFocus>
            Top up
          </Button>
        </>
      }
    >
      {c && (
        <PaletteScope paletteId={c.paletteId} className={s.head}>
          <PortraitCard character={c} emotion="neutral" size="head" width={64} energyState={e?.state} parallax={false} />
          <div className={s.meter}>
            <span className={s.name}>{c.profile.name}</span>
            <EnergyBar characterId={characterId} size="chat" showLabel label={name} />
          </div>
        </PaletteScope>
      )}
      <div className={s.opts} role="radiogroup" aria-label="Top-up amount">
        {options.map((o) => (
          <button key={o} type="button" role="radio" aria-checked={pts === o} className={cx(s.opt, pts === o && s.optOn)} onClick={() => setPts(o)}>
            <span className={s.optBig}>⚡ +{o}</span>
            <span className={s.optCost}>≈ US{formatUsd(o * usdPer)}</span>
          </button>
        ))}
      </div>
      <p className={s.fine}>
        Counts against today's cap: {formatUsd(spent)} of {formatUsd(cap)} spent. {e && e.state === "exhausted" ? `${name} wakes up right away.` : ""}
      </p>
    </Modal>
  );
}
