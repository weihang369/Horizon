// O26: foundation stub (Builder D replaces it). Owner: EE (stub).
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { StubOverlay } from "../../app/stubs";

export function EndDebate({ close, layerKey: _k, ...props }: OverlayComponentProps<"O26">) {
  return <StubOverlay id="O26" close={close}><code>{JSON.stringify(props, (_k, v) => (typeof v === "function" ? "ƒ" : v))}</code></StubOverlay>;
}
