// O11: foundation stub (Builder C replaces it). Owner: EE (stub).
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { StubOverlay } from "../../app/stubs";

export function MentionPicker({ close, layerKey: _k, ...props }: OverlayComponentProps<"O11">) {
  return <StubOverlay id="O11" close={close}><code>{JSON.stringify(props, (_k, v) => (typeof v === "function" ? "ƒ" : v))}</code></StubOverlay>;
}
