// O13: foundation stub (Builder B replaces it). Owner: EE (stub).
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { StubOverlay } from "../../app/stubs";

export function UnsavedDraft({ close, layerKey: _k, ...props }: OverlayComponentProps<"O13">) {
  return <StubOverlay id="O13" close={close}><code>{JSON.stringify(props, (_k, v) => (typeof v === "function" ? "ƒ" : v))}</code></StubOverlay>;
}
