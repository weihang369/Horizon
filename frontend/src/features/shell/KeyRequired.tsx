// O05 Key required (STATE-04): foundation stub (Builder A replaces it). Owner: EE (stub).
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { navigate } from "../../router";
import { Button } from "../../ui/Button";
import { Modal } from "../../ui/Panels";

export function KeyRequired({ close, reason }: OverlayComponentProps<"O05">) {
  return (
    <Modal
      title="Add your OpenRouter key"
      tape="KEY REQUIRED"
      size="sm"
      onClose={close}
      actions={
        <>
          <Button variant="ghost" onClick={close}>Not now</Button>
          <Button onClick={() => { close(); navigate({ name: "settings", tab: "connection", from: location.hash.slice(1) }); }}>Add key</Button>
        </>
      }
    >
      <p>{reason ?? "Horizon needs your OpenRouter key to think. Recordings still play without one."}</p>
    </Modal>
  );
}
