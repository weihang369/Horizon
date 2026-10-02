// O20: foundation stub (Builder A replaces it). Owner: EE (stub).
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { StubOverlay } from "../../app/stubs";

export function ShortcutsSheet({ close, layerKey: _k, ...props }: OverlayComponentProps<"O20">) {
  return <StubOverlay id="O20" close={close}><code>{JSON.stringify(props, (_k, v) => (typeof v === "function" ? "ƒ" : v))}</code></StubOverlay>;
}
