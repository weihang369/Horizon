// O02: foundation stub (Builder A replaces it). Owner: EE (stub).
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { StubOverlay } from "../../app/stubs";

export function WorldEditor({ close, layerKey: _k, ...props }: OverlayComponentProps<"O02">) {
  return <StubOverlay id="O02" close={close}><code>{JSON.stringify(props, (_k, v) => (typeof v === "function" ? "ƒ" : v))}</code></StubOverlay>;
}
