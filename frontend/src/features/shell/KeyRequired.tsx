// O05 Key required (STATE-04, R15): compact modal — "Add key" deep-links to Settings → Connection, "Not now" keeps
// browsing. Recordings always play without a key. Owner: Builder A.
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { getRoute, navigate } from "../../router";
import { formatRoute } from "../../router/routes";
import { Button } from "../../ui/Button";
import { Modal } from "../../ui/Panels";
import { KeyIcon } from "../../ui/icons";
import s from "./Overlays.module.css";

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
          <Button autoFocus icon={<KeyIcon />} onClick={() => { close(); navigate({ name: "settings", tab: "connection", from: formatRoute(getRoute()) }); }}>Add key</Button>
        </>
      }
    >
      <div className={s.keyReq}>
        <span className={s.keyGlyph} aria-hidden="true"><KeyIcon width={34} height={34} /></span>
        <div>
          <p className={s.keyLead}>{reason ?? "Horizon needs your OpenRouter key to think."}</p>
          <p className={s.keyNote}>Recordings, profiles and Insight still work without one. Your key stays on this machine.</p>
        </div>
      </div>
    </Modal>
  );
}
