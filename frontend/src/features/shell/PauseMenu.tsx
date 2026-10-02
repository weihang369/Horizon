// O01 Pause menu: foundation stub (Builder A replaces it). Owner: EE (stub).
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { getRoute, navigate } from "../../router";
import type { Route } from "../../router";
import { Button } from "../../ui/Button";
import { Modal } from "../../ui/Panels";

export function PauseMenu({ close }: OverlayComponentProps<"O01">) {
  const r = getRoute();
  const worldId = "worldId" in r ? r.worldId : undefined;
  const go = (to: Route) => {
    close();
    navigate(to);
  };
  return (
    <Modal title="O01 · Paused" tape="PAUSE" onClose={close}>
      <Button block onClick={close}>Resume</Button>
      <Button block variant="secondary" onClick={() => go({ name: "worlds" })}>Worlds</Button>
      {worldId && <Button block variant="secondary" onClick={() => go({ name: "hub", worldId })}>World Hub</Button>}
      {worldId && <Button block variant="secondary" onClick={() => go({ name: "hub", worldId, tab: "sessions" })}>History</Button>}
      <Button block variant="secondary" onClick={() => go({ name: "settings", from: location.hash.slice(1) })}>Settings</Button>
      <Button block variant="ghost" onClick={() => go({ name: "title" })}>Title</Button>
    </Modal>
  );
}
