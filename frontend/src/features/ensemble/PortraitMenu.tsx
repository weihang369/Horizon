// O24: foundation stub (Builder D replaces it). Owner: EE (stub).
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { StubOverlay } from "../../app/stubs";

export function PortraitMenu({ close, layerKey: _k, ...props }: OverlayComponentProps<"O24">) {
  return <StubOverlay id="O24" close={close}><code>{JSON.stringify(props, (_k, v) => (typeof v === "function" ? "ƒ" : v))}</code></StubOverlay>;
}
