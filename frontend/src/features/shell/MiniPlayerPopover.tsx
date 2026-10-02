// O09: foundation stub (Builder A replaces it). Owner: EE (stub).
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { StubOverlay } from "../../app/stubs";

export function MiniPlayerPopover({ close, layerKey: _k, ...props }: OverlayComponentProps<"O09">) {
  return <StubOverlay id="O09" close={close}><code>{JSON.stringify(props, (_k, v) => (typeof v === "function" ? "ƒ" : v))}</code></StubOverlay>;
}
