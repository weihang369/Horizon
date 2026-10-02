// O22 Demo-mode tape (APP-09 AC1): foundation stub (Builder A replaces it). Owner: EE (stub). App mounts it in demo mode.
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { navigate } from "../../router";
import { Tape } from "../../ui/Tape";

export function DemoTape(_: Partial<OverlayComponentProps<"O22">>) {
  return (
    <button
      type="button"
      onClick={() => navigate({ name: "settings", tab: "connection", from: location.hash.slice(1) })}
      style={{ all: "unset", cursor: "pointer", display: "block" }}
    >
      <Tape tone="brand" size="sm">O22 · DEMO MODE · Browsing seed data · Add your OpenRouter key to chat &amp; create</Tape>
    </button>
  );
}
