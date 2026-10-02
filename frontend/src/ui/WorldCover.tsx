// <WorldCover> — the 8 CSS/SVG presets (or an uploaded/generated image URL). Owner: VMD.
import type { CSSProperties, ReactNode } from "react";
import type { World } from "../contract/types";
import { getCoverPreset } from "../vfx/covers";
import s from "./WorldCover.module.css";
import { cx } from "./cx";

export interface WorldCoverProps {
  /** A World.cover, or pass presetId directly. */
  cover?: World["cover"];
  presetId?: string;
  /** Adds the house chrome: corner halftone + 14° horizon-500 hairline. Default true. */
  chrome?: boolean;
  /** Accessible label; omit for decorative covers. */
  label?: string;
  className?: string;
  style?: CSSProperties;
  children?: ReactNode;
}

export function WorldCover({ cover, presetId, chrome = true, label, className, style, children }: WorldCoverProps) {
  const url = cover && cover.kind !== "preset" ? cover.url : undefined;
  const preset = getCoverPreset(presetId ?? cover?.presetId);
  const bg = url ? `center / cover no-repeat url("${url}")` : preset.background;
  return (
    <div
      className={cx(s.cover, className)}
      style={{ ...style, background: bg }}
      role={label ? "img" : undefined}
      aria-label={label}
      data-cover={url ? "image" : preset.id}
    >
      {!url && preset.grid && (
        <div className={s.gridWrap} aria-hidden="true">
          <div className={s.grid} />
        </div>
      )}
      {chrome && <div className={s.chrome} aria-hidden="true" />}
      {children}
    </div>
  );
}
