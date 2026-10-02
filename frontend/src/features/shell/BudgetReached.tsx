// O21 Budget reached (STATE-06): foundation stub (Builder A replaces it). Owner: EE (stub).
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { formatUsd } from "../../domain/format";
import { navigate } from "../../router";
import { Button } from "../../ui/Button";
import { Modal } from "../../ui/Panels";

export function BudgetReached({ close, scope, spentUsd, capUsd }: OverlayComponentProps<"O21">) {
  return (
    <Modal
      title="Budget reached"
      tape="BUDGET"
      size="sm"
      onClose={close}
      actions={
        <>
          <Button variant="ghost" onClick={close}>Stop here</Button>
          <Button onClick={() => { close(); navigate({ name: "settings", tab: "cost", from: location.hash.slice(1) }); }}>Raise cap</Button>
        </>
      }
    >
      <p>{scope === "daily" ? "Today's" : "This character's creation"} budget is reached: {formatUsd(spentUsd)} of {formatUsd(capUsd)}.</p>
    </Modal>
  );
}
