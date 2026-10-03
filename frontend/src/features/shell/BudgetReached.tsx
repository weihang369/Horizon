// O21 Budget reached (STATE-06): pauses the session/generation; "Raise cap" deep-links to Settings → Cost,
// "Stop here" leaves it paused (the session shows its daily_budget banner). Owner: Builder A.
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { formatUsd } from "../../domain/format";
import { getRoute, navigate } from "../../router";
import { formatRoute } from "../../router/routes";
import { Button } from "../../ui/Button";
import { Modal } from "../../ui/Panels";
import s from "./Overlays.module.css";

export function BudgetReached({ close, scope, spentUsd, capUsd, sessionId }: OverlayComponentProps<"O21">) {
  const pct = capUsd > 0 ? Math.min(1, spentUsd / capUsd) : 1;
  const what = scope === "daily" ? "Today's spending cap" : "This character's creation cap";
  return (
    <Modal
      title="Budget reached"
      tape={scope === "daily" ? "DAILY CAP" : "CREATION CAP"}
      tapeTone="warn"
      size="sm"
      onClose={close}
      actions={
        <>
          <Button variant="ghost" onClick={close}>Stop here</Button>
          <Button autoFocus onClick={() => { close(); navigate({ name: "settings", tab: "cost", from: formatRoute(getRoute()) }); }}>Raise cap ▸</Button>
        </>
      }
    >
      <div className={s.budget}>
        <p className={s.budgetLead}>{what} is used up, so Horizon paused {sessionId ? "this session" : "the generation"}. Nothing else is spent until you raise it or tomorrow begins.</p>
        <div className={s.meter} role="meter" aria-valuemin={0} aria-valuemax={capUsd} aria-valuenow={spentUsd} aria-label="Spent of cap">
          <span className={s.meterFill} style={{ transform: `scaleX(${pct})` }} />
        </div>
        <p className={s.budgetNums}><b>{formatUsd(spentUsd)}</b> of {formatUsd(capUsd)}</p>
      </div>
    </Modal>
  );
}
