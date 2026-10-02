// Spec card column (CHR-06 layout): the current base portrait (or the "?" silhouette), framed in the provisional
// palette, the name plate from the working profile, and a compact character sheet. Owner: Builder B.
import type { CSSProperties } from "react";
import { useSong } from "@/client/hooks";
import type { Character, Emotion } from "@/contract/types";
import { EMOTIONS } from "@/contract/types";
import { NamePlate, PortraitCard } from "@/character";
import type { PortraitCharacter } from "@/character";
import { getPalette } from "@/theme";
import { Tape } from "@/ui";
import { cx } from "@/ui/cx";
import { useWizard } from "./context";
import { INTENTS } from "./options";
import s from "./wizard.module.css";

const BLANK: PortraitCharacter = {
  id: "new", paletteId: "pal_house",
  emotions: Object.fromEntries(EMOTIONS.map((e) => [e, null])) as Character["emotions"],
  profile: { name: "?", role: "" },
};

export function SpecCard({ preview }: { preview?: { paletteId?: string } }) {
  const { character: c, work, step } = useWizard();
  const song = useSong(c?.id).data;
  const paletteId = preview?.paletteId ?? c?.paletteId ?? null;
  const pc: PortraitCharacter = c
    ? { ...c, paletteId: paletteId ?? c.paletteId, profile: { ...c.profile, name: work.w.profile.name || "?", role: work.w.profile.role } }
    : BLANK;
  const pal = getPalette(paletteId);
  const emotionsReady = c ? EMOTIONS.filter((e: Emotion) => !!c.emotions[e]).length : 0;
  const look = step === "look";
  const at = work.w.attributes;
  return (
    <aside className={s.spec} aria-label="Character spec card">
      <div className={s.specPortrait}>
        <PortraitCard character={pc} emotion="neutral" size="hero" width="var(--spec-w)" parallax={!!c?.appearance.basePortraitUrl} />
        {!c?.appearance.basePortraitUrl && (
          <span className={s.specUnknown}><Tape tone="ink" size="sm">{c ? "No portrait yet" : "Who?"}</Tape></span>
        )}
        {c?.appearance.basePortraitUrl && <span className={s.specLock} aria-label="Base portrait locked">🔒 BASE</span>}
        {look && (
          <>
            <span className={s.specBadge}><Tape tone="brand" size="sm" rotate={-4}>Changes apply on Generate</Tape></span>
            <span className={s.fabric} aria-label={`Outfit colours ${at.outfit.primaryColor} and ${at.outfit.secondaryColor}`}>
              <span style={{ "--sw": at.outfit.primaryColor } as CSSProperties} />
              <span style={{ "--sw": at.outfit.secondaryColor } as CSSProperties} />
            </span>
          </>
        )}
      </div>
      {c && (work.w.profile.name || work.w.profile.role) && (
        <NamePlate className={s.specPlate} character={pc} size="md" subtitle={work.w.profile.role || "—"} />
      )}
      {c && (
        <dl className={s.sheet}>
          <div><dt>Age</dt><dd>{work.w.profile.age || "—"}</dd></div>
          <div><dt>Intent</dt><dd>{INTENTS.find((i) => i.value === c.intent)?.label.split(" ")[0] ?? "—"}</dd></div>
          <div><dt>Palette</dt><dd className={s.sheetPal}><i style={{ "--sw": pal.primary } as CSSProperties} />{pal.name}</dd></div>
          <div><dt>Faces</dt><dd className={cx(emotionsReady < 2 && s.sheetDim)}>{emotionsReady} / 7</dd></div>
          <div><dt>Theme</dt><dd className={cx(!song || song.status !== "ready" ? s.sheetDim : undefined)}>{song?.status === "ready" ? "♪ Ready" : song?.status === "failed" ? "Failed" : "Not yet"}</dd></div>
        </dl>
      )}
      {!c && (
        <p className={s.specHint}>One line is enough. The AI drafts the profile, look, palette and theme brief; you edit everything after.</p>
      )}
    </aside>
  );
}
