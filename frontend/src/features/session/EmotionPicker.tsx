// O07: foundation stub (Builder C replaces it). Owner: EE (stub).
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { StubOverlay } from "../../app/stubs";

export function EmotionPicker({ close, layerKey: _k, ...props }: OverlayComponentProps<"O07">) {
  return <StubOverlay id="O07" close={close}><code>{JSON.stringify(props, (_k, v) => (typeof v === "function" ? "ƒ" : v))}</code></StubOverlay>;
}
