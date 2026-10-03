// O28 Source viewer (D-59): a knowledge source's passages, scrolled to the cited one. Owner: Builder B.
// Stub so the overlay registry type-checks; Builder B replaces it.
import type { OverlayComponentProps } from "../../app/overlayTypes";

export function SourceViewer({ close }: OverlayComponentProps<"O28">) {
  return <button type="button" onClick={close}>Close</button>;
}
