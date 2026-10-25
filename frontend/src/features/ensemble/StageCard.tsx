// One stage portrait for S09/S10/S12 (Builder D). Wraps the kit's <PortraitCard> with the O24 portrait menu:
// click, right-click, Enter, Shift+F10 or the ContextMenu key all open the same menu (MULTI-17, D-50: one gesture,
// one meaning). ←/→ move focus between stage portraits (UXA §2.3 roving focus).
import type { CSSProperties, KeyboardEvent, MouseEvent } from "react";
import type { Character, Emotion, EnergyState } from "../../contract/types";
import { PortraitCard } from "../../character";
import type { PortraitSize } from "../../character";
import { openOverlay } from "../../app/layers";

export interface StageCardProps {
  sessionId: string;
  character: Character;
  emotion: Emotion;
  size?: PortraitSize;
  width?: number | string;
  speaking?: boolean;
  listening?: boolean;
  dimmed?: boolean;
  energyState?: EnergyState;
  reaction?: { emotion: Emotion; key: string } | null;
  showPlate?: boolean;
  showEnergy?: boolean;
  plateSubtitle?: string | null;
  className?: string;
  style?: CSSProperties;
}

function openMenu(sessionId: string, characterId: string, el: HTMLElement, at?: { x: number; y: number }) {
  // Keyboard: anchor on the card's lower third (the plate sits just below), so the menu stays near the face.
  const r = el.getBoundingClientRect();
  const anchor = at ? { x: at.x, y: at.y, width: 1, height: 1 } : { x: r.left + 16, y: r.top + r.height * 0.62, width: r.width - 32, height: 1 };
  openOverlay("O24", { sessionId, characterId, anchor });
}

/** Focus the previous/next stage portrait in DOM order. */
export function moveStageFocus(from: HTMLElement, dir: 1 | -1): void {
  const root = from.closest("[data-stage-root]") ?? document;
  const all = [...root.querySelectorAll<HTMLElement>("[data-stage-portrait]")];
  const i = all.indexOf(from);
  const next = all[(i + dir + all.length) % all.length];
  next?.focus();
}

export function StageCard({
  sessionId, character, emotion, size = "stage", width, speaking, listening, dimmed, energyState, reaction,
  showPlate, showEnergy, plateSubtitle, className, style,
}: StageCardProps) {
  const onClick = (e: MouseEvent<HTMLDivElement>) => {
    const pointer = e.detail > 0 && e.clientX > 0;
    openMenu(sessionId, character.id, e.currentTarget, pointer ? { x: e.clientX - 12, y: e.clientY + 4 } : undefined);
  };
  const onContextMenu = (e: MouseEvent<HTMLDivElement>) => {
    e.preventDefault();
    openMenu(sessionId, character.id, e.currentTarget, { x: e.clientX - 12, y: e.clientY + 4 });
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if ((e.key === "F10" && e.shiftKey) || e.key === "ContextMenu") {
      e.preventDefault();
      openMenu(sessionId, character.id, e.currentTarget);
    } else if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      moveStageFocus(e.currentTarget, e.key === "ArrowRight" ? 1 : -1);
    }
  };
  return (
    <PortraitCard
      character={character}
      emotion={emotion}
      size={size}
      width={width}
      speaking={speaking}
      listening={listening}
      dimmed={dimmed}
      energyState={energyState}
      reaction={reaction}
      showPlate={showPlate}
      showEnergy={showEnergy}
      plateSubtitle={plateSubtitle}
      onClick={onClick}
      onContextMenu={onContextMenu}
      onKeyDown={onKeyDown}
      aria-haspopup="menu"
      data-stage-portrait=""
      className={className}
      style={style}
    />
  );
}
