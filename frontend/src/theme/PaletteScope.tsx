// <PaletteScope paletteId> — scopes a palette's CSS variables to a subtree (R9). Owner: VMD.
import type { CSSProperties, ElementType, ReactNode } from "react";
import { paletteClass } from "./palettes";

export interface PaletteScopeProps {
  paletteId: string | null | undefined;
  /** Element to render (default `div`). Use `contents` to avoid a layout box. */
  as?: ElementType;
  className?: string;
  style?: CSSProperties;
  children?: ReactNode;
}

export function PaletteScope({ paletteId, as: Tag = "div", className, style, children }: PaletteScopeProps) {
  const cls = [paletteClass(paletteId), className].filter(Boolean).join(" ");
  return (
    <Tag className={cls} style={style} data-palette={paletteId ?? "pal_house"}>
      {children}
    </Tag>
  );
}
