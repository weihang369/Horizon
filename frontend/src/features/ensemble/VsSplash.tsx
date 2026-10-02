// O16: foundation stub (Builder D replaces it). Owner: EE (stub).
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { StubOverlay } from "../../app/stubs";

export function VsSplash({ close, layerKey: _k, ...props }: OverlayComponentProps<"O16">) {
  return <StubOverlay id="O16" close={close}><code>{JSON.stringify(props, (_k, v) => (typeof v === "function" ? "ƒ" : v))}</code></StubOverlay>;
}
