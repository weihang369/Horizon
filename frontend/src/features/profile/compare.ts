// O25 trigger (PRF-03 AC5): when a regeneration for an APPROVED character finishes, the new asset arrives inactive;
// open the Old | New comparison so the user chooses. Owner: Builder B.
import { useEffect } from "react";
import { openOverlay } from "@/app/layers";
import { client } from "@/client";
import { useJob } from "@/client/hooks";
import type { Character } from "@/contract/types";

/** Jobs already compared this app session (each regeneration asks once). */
const handled = new Set<string>();

export function useAssetCompareWatcher(c: Character | null | undefined, jobId: string | undefined): void {
  const job = useJob(jobId).data;
  useEffect(() => {
    if (!c || !job || c.status !== "approved" || job.kind !== "emotion_regenerate") return;
    if (job.status !== "succeeded" && job.status !== "partial") return;
    if (handled.has(job.id)) return;
    handled.add(job.id);
    const ids = new Set(job.tasks.map((t) => t.resultRef).filter(Boolean));
    void client.characters.assets(c.id).then((assets) => {
      const fresh = assets.filter((a) => ids.has(a.id) && !a.isActive);
      for (const a of fresh) openOverlay("O25", { characterId: c.id, emotion: a.emotion, newAssetId: a.id });
    }).catch(() => {});
  }, [c, job]);
}
