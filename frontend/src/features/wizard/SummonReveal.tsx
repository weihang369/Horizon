// O15: foundation stub (Builder B replaces it). Owner: EE (stub).
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { StubOverlay } from "../../app/stubs";

export function SummonReveal({ close, layerKey: _k, ...props }: OverlayComponentProps<"O15">) {
  return <StubOverlay id="O15" close={close}><code>{JSON.stringify(props, (_k, v) => (typeof v === "function" ? "ƒ" : v))}</code></StubOverlay>;
}
