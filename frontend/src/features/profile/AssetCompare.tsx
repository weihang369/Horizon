// O25: foundation stub (Builder B replaces it). Owner: EE (stub).
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { StubOverlay } from "../../app/stubs";

export function AssetCompare({ close, layerKey: _k, ...props }: OverlayComponentProps<"O25">) {
  return <StubOverlay id="O25" close={close}><code>{JSON.stringify(props, (_k, v) => (typeof v === "function" ? "ƒ" : v))}</code></StubOverlay>;
}
