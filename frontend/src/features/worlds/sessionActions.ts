// History row actions (S13, HIST-02/03, R15/R16): replay, resume, continue live, rename, export, delete. Owner: Builder A.
import { openOverlay, toast } from "../../app/layers";
import { client } from "../../client";
import type { HorizonErrorShape } from "../../contract/errors";
import type { Session } from "../../contract/types";
import { navigate } from "../../router";
import { resumeRoute } from "./hubLogic";

const msg = (e: unknown, fallback: string) => (e as HorizonErrorShape)?.message ?? fallback;

export function replaySession(s: Session): void {
  navigate({ name: "session", worldId: s.worldId, sessionId: s.id, replay: true });
}

export function resumeSession(s: Session): void {
  navigate(resumeRoute(s));
}

/** "Continue live" (D-51): forks the whole recording (no playhead from History). Demo mode asks for a key (R15). */
export async function continueLive(s: Session, demo: boolean): Promise<void> {
  if (demo) {
    openOverlay("O05", { reason: "Continuing a recording live needs your OpenRouter key. The recording itself always stays as shipped." });
    return;
  }
  try {
    const snap = await client.sessions.forkSeedSession(s.id);
    toast({ variant: "success", text: `Live copy of “${s.title}”` });
    navigate({ name: "session", worldId: s.worldId, sessionId: snap.session.id });
  } catch (e) {
    if ((e as HorizonErrorShape)?.code === "missing_key" || (e as HorizonErrorShape)?.code === "invalid_key") openOverlay("O05", {});
    else toast({ variant: "error", text: msg(e, "Couldn't continue this session.") });
  }
}

export async function renameSession(s: Session, title: string): Promise<boolean> {
  const t = title.trim();
  if (!t || t === s.title) return false;
  try {
    await client.sessions.rename(s.id, t.slice(0, 80));
    toast({ variant: "success", text: "Renamed." });
    return true;
  } catch (e) {
    toast({ variant: "error", text: msg(e, "Couldn't rename.") });
    return false;
  }
}

export async function exportSession(s: Session): Promise<void> {
  try {
    const md = await client.sessions.export(s.id);
    const blob = new Blob([md], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${s.title.replace(/[^\w\- ]+/g, "").trim().replace(/\s+/g, "-").toLowerCase() || s.id}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    toast({ variant: "success", text: "Exported as Markdown." });
  } catch (e) {
    toast({ variant: "error", text: msg(e, "Couldn't export.") });
  }
}

/** Simple confirm (O03, doc 03 §2). */
export function deleteSession(s: Session): void {
  openOverlay("O03", {
    title: `Delete “${s.title}”?`,
    body: s.isSeed
      ? "This removes the recording from this browser. “Reset demo data” in Settings → Data brings it back."
      : `${s.messageCount} message${s.messageCount === 1 ? "" : "s"} will be deleted. Characters keep their memories.`,
    confirmLabel: "Delete session",
    onConfirm: async () => {
      await client.sessions.delete(s.id);
      toast({ variant: "info", text: `Deleted “${s.title}”.` });
    },
  });
}
