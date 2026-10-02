// O04 Cost confirmation (CHR-13 AC1): first generation per app launch, can be switched off. Owner: Builder B.
import { useState } from "react";
import type { OverlayComponentProps } from "@/app/overlayTypes";
import { run } from "@/app/errors";
import { client } from "@/client";
import { useSettings } from "@/client/hooks";
import { formatUsd } from "@/domain/format";
import { Button, Modal, Toggle } from "@/ui";
import s from "./overlays.module.css";

export function CostConfirm({ close, label, estimateUsd, onConfirm }: OverlayComponentProps<"O04">) {
  const settings = useSettings().data;
  const [dontAsk, setDontAsk] = useState(false);

  const spent = settings?.spentTodayUsd ?? 0;
  const cap = settings?.budget.dailyCapUsd ?? 1;
  const after = Math.min(1, (spent + estimateUsd) / cap);
  const go = () => {
    if (dontAsk) void run(() => client.settings.update({ cost: { confirmBeforeGenerate: false } }));
    onConfirm();
    close();
  };

  return (
    <Modal
      title="Spend a little?"
      tape="O04 · COST CHECK"
      size="sm"
      onClose={close}
      actions={
        <>
          <Button variant="ghost" onClick={close}>Not now</Button>
          <Button variant="primary" autoFocus onClick={go} cost={estimateUsd}>Generate</Button>
        </>
      }
    >
      <div className={s.cost}>
        <p className={s.costLabel}>{label}</p>
        <div className={s.costFigure} aria-label={`Estimated cost ${formatUsd(estimateUsd, { approx: true })}`}>
          <span className={s.costApprox}>≈</span>
          <span className={s.costUsd}>{formatUsd(estimateUsd).replace(/^≈\s*/, "")}</span>
        </div>
        <div className={s.costBar} role="img" aria-label={`Today ${formatUsd(spent)} of ${formatUsd(cap)}; after this ${Math.round(after * 100)} %`}>
          <span className={s.costBarNow} style={{ transform: `scaleX(${Math.min(1, spent / cap)})` }} />
          <span className={s.costBarAfter} style={{ transform: `scaleX(${after})` }} />
        </div>
        <p className={s.costMeta}>
          Today {formatUsd(spent)} of your {formatUsd(cap)} daily cap. Estimates come from the pricing table; the
          real charge shows in Settings → Cost.
        </p>
        <p className={s.costFine}>We ask once per launch. Images already in progress may still be charged if you cancel them.</p>
        <Toggle checked={dontAsk} onChange={setDontAsk} label="Don't ask again" />
      </div>
    </Modal>
  );
}
