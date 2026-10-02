// O10: foundation stub (Builder C replaces it). Owner: EE (stub).
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { StubOverlay } from "../../app/stubs";

export function Backlog({ close, layerKey: _k, ...props }: OverlayComponentProps<"O10">) {
  return <StubOverlay id="O10" close={close}><code>{JSON.stringify(props, (_k, v) => (typeof v === "function" ? "ƒ" : v))}</code></StubOverlay>;
}
