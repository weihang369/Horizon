// <NamePlate> (spec §3.5, VMD paper §2.2): a primary bar at −8° with the name in Anton (onPrimary),
// over an ink role strip offset 10 px right. Scoped to the character's palette (R9). Owner: VMD.
import type { CSSProperties, ReactNode } from "react";
import type { Character } from "../contract/types";
import { PaletteScope } from "../theme/PaletteScope";
import { cx } from "../ui/cx";
import s from "./NamePlate.module.css";

export type NamePlateCharacter = Pick<Character, "id" | "paletteId"> & { profile: Pick<Character["profile"], "name" | "role"> & { title?: string } };

export interface NamePlateProps {
  character: NamePlateCharacter;
  size?: "lg" | "md" | "sm";
  /** Replaces the role strip (e.g. "ASLEEP · ⚡0", "PROP · 1st speaker"). Pass null to hide it. */
  subtitle?: ReactNode | null;
  /** Additive: prepend the honorific (Dr.). Default false. */
  showTitle?: boolean;
  className?: string;
  style?: CSSProperties;
}

export function NamePlate({ character, size = "md", subtitle, showTitle, className, style }: NamePlateProps) {
  const p = character.profile;
  const name = showTitle && p.title ? `${p.title} ${p.name}` : p.name;
  const sub = subtitle === undefined ? p.role : subtitle;
  return (
    <PaletteScope paletteId={character.paletteId} className={cx(s.plate, s[size], className)} style={style}>
      <span className={s.bar}>
        <span className={s.name}>{name}</span>
      </span>
      {sub !== null && sub !== "" && <span className={s.role}>{sub}</span>}
    </PaletteScope>
  );
}
