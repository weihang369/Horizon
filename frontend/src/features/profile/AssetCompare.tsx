// O25 Old / New asset comparison (PRF-03 AC5): the old version stays active until the user picks. Owner: Builder B.
import { useEffect, useState } from "react";
import type { OverlayComponentProps } from "@/app/overlayTypes";
import { reportError } from "@/app/errors";
import { toast } from "@/app/layers";
import { audio } from "@/audio/engine";
import { client } from "@/client";
import { useCharacter } from "@/client/hooks";
import type { EmotionAsset } from "@/contract/types";
import { emotionMeta } from "@/character";
import { PaletteScope } from "@/theme";
import { Button, Modal, Tape } from "@/ui";
import { cx } from "@/ui/cx";
import s from "./profile-overlays.module.css";

export function AssetCompare({ close, characterId, emotion, newAssetId }: OverlayComponentProps<"O25">) {
  const c = useCharacter(characterId).data;
  const [assets, setAssets] = useState<EmotionAsset[] | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    void client.characters.assets(characterId).then(setAssets).catch((e) => reportError(e));
  }, [characterId]);

  const fresh = assets?.find((a) => a.id === newAssetId);
  const old = assets?.find((a) => a.emotion === emotion && a.variant === (fresh?.variant ?? "default") && a.isActive && a.id !== newAssetId);
  const label = emotionMeta[emotion].label;

  const useNew = async () => {
    setBusy(true);
    try {
      await client.characters.acceptAssetVersion(newAssetId);
      audio.playSfx("ui_confirm");
      toast({ variant: "success", text: `New ${label.toLowerCase()} face is live.` });
      close();
    } catch (err) {
      reportError(err);
      setBusy(false);
    }
  };

  return (
    <PaletteScope paletteId={c?.paletteId} as="div" className={s.compareScope}>
      <Modal
        title={`${label}: old or new?`}
        tape="O25 · COMPARE"
        tapeTone="primary"
        size="lg"
        onClose={close}
        actions={
          <>
            <Button variant="ghost" onClick={close}>Keep old</Button>
            <Button variant="primary" autoFocus disabled={busy || !fresh} onClick={() => void useNew()}>Use new</Button>
          </>
        }
      >
        <div className={s.compare}>
          {[{ a: old, tag: "OLD · ACTIVE", side: "old" }, { a: fresh, tag: "NEW", side: "new" }].map(({ a, tag, side }) => (
            <figure key={side} className={cx(s.cmpCard, side === "new" && s.cmpNew)}>
              <div className={s.cmpFrame}>
                {a?.url ? <img src={a.url} alt={`${side} ${label}`} draggable={false} /> : <span className={s.cmpEmpty}>{assets ? "No earlier version" : "Loading…"}</span>}
                <span className={s.cmpTag}><Tape tone={side === "new" ? "primary" : "ink"} size="sm">{tag}</Tape></span>
              </div>
              <figcaption className={s.cmpCap}>
                {a ? `v${a.version} · ${a.generation?.technique?.replace(/_/g, " ") ?? "manual"}${a.generation ? ` · $${a.generation.costUsd.toFixed(3)}` : ""}` : "—"}
              </figcaption>
            </figure>
          ))}
        </div>
        <p className={s.cmpNote}>Nothing changes until you choose. Keep old leaves the new version in the asset history.</p>
      </Modal>
    </PaletteScope>
  );
}
