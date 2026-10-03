// O01 Pause menu (APP-02, R4, R13): Esc outside fields/modals or the ☰ button. Resume · Worlds · World Hub ·
// History (deep link: hub ?tab=sessions) · Settings · How it works (replays S02) · Title, with the current world and active character.
// ↑/↓ move, Enter picks, Esc again resumes (LayerStack). Owner: Builder A.
import { useEffect, useRef } from "react";
import type { KeyboardEvent } from "react";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { audio } from "../../audio/engine";
import { useCharacter, useCharacters, useSessions, useWorld } from "../../client/hooks";
import type { Route } from "../../router";
import { getRoute, navigate } from "../../router";
import { formatRoute } from "../../router/routes";
import { RansomText } from "../../ui/RansomText";
import { Tape } from "../../ui/Tape";
import { WorldCover } from "../../ui/WorldCover";
import { headUrl } from "../worlds/portraitUrls";
import s from "./Overlays.module.css";

interface Item { id: string; label: string; hint?: string; to?: Route; disabled?: boolean }

export function PauseMenu({ close }: OverlayComponentProps<"O01">) {
  const route = useRef(getRoute()).current;
  const worldId = "worldId" in route ? route.worldId : undefined;
  const world = useWorld(worldId).data;
  const sessions = useSessions(route.name === "session" || route.name === "verdict" ? worldId : null).data;
  const session = route.name === "session" || route.name === "verdict" ? sessions?.find((x) => x.id === route.sessionId) : undefined;
  const profileChar = useCharacter(route.name === "profile" || (route.name === "wizard" && route.characterId) ? (route as { characterId?: string }).characterId : null).data;
  const chars = useCharacters(session ? worldId : null, { includeArchived: true }).data;
  const cast = session ? session.participants.map((p) => chars?.find((c) => c.id === p.characterId)).filter((c) => !!c) : profileChar ? [profileChar] : [];

  const items: Item[] = [
    { id: "resume", label: "Resume" },
    { id: "worlds", label: "Worlds", to: { name: "worlds" } },
    { id: "hub", label: "World Hub", hint: world?.name, to: worldId ? { name: "hub", worldId } : undefined, disabled: !worldId },
    { id: "history", label: "History", hint: worldId ? "Sessions in this world" : undefined, to: worldId ? { name: "hub", worldId, tab: "sessions" } : undefined, disabled: !worldId },
    { id: "settings", label: "Settings", to: { name: "settings", from: formatRoute(route) } },
    { id: "intro", label: "How it works", hint: "Replay the intro", to: { name: "onboarding", card: 1 } },
    { id: "title", label: "Title", to: { name: "title" } },
  ];

  const list = useRef<HTMLUListElement>(null);
  useEffect(() => {
    audio.playSfx("ui_pause_open");
    list.current?.querySelector<HTMLButtonElement>("button")?.focus();
  }, []);

  const pick = (it: Item) => {
    if (it.disabled) return;
    if (it.id === "resume") {
      audio.playSfx("ui_pause_close");
      close();
      return;
    }
    close();
    if (it.to) navigate(it.to, it.id === "title" || it.id === "worlds" ? { transition: "slash-back" } : undefined);
  };
  const onKey = (e: KeyboardEvent<HTMLUListElement>) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp" && e.key !== "Home" && e.key !== "End") return;
    e.preventDefault();
    const btns = [...(list.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? [])];
    const i = btns.indexOf(document.activeElement as HTMLButtonElement);
    const n = e.key === "Home" ? 0 : e.key === "End" ? btns.length - 1 : (i + (e.key === "ArrowDown" ? 1 : -1) + btns.length) % btns.length;
    btns[n]?.focus();
    audio.playSfx("ui_hover");
  };

  return (
    <div className={s.pause} role="dialog" aria-modal="true" aria-label="Paused">
      <div className={s.pauseSlab} aria-hidden="true" />
      <div className={s.pauseGhost} aria-hidden="true">PAUSE</div>
      <div className={s.pauseLeft}>
        <h2 className={s.pauseTitle}>
          <RansomText text="PAUSED" size={64} tone="mixed" slam staggerMs={30} />
        </h2>
        <ul ref={list} className={s.pauseList} onKeyDown={onKey}>
          {items.map((it, i) => (
            <li key={it.id} style={{ ["--i" as string]: i }}>
              <button type="button" className={s.pauseItem} disabled={it.disabled} onClick={() => pick(it)} onMouseEnter={(e) => e.currentTarget.focus()}>
                <span className={s.pauseItemFill} aria-hidden="true" />
                <span className={s.pauseLabel}>{it.label}</span>
                {it.hint && <span className={s.pauseHint}>{it.hint}</span>}
              </button>
            </li>
          ))}
        </ul>
        <p className={s.pauseKeys} aria-hidden="true">↑ ↓ choose · Enter select · Esc resume</p>
      </div>
      <aside className={s.pauseRight} aria-label="Where you are">
        {world ? (
          <div className={s.pauseWorld}>
            <WorldCover cover={world.cover} className={s.pauseCover} />
            <div className={s.pauseWorldInfo}>
              <Tape tone="paper" size="sm">CURRENT WORLD</Tape>
              <span className={s.pauseWorldName}>{world.name}</span>
              {session && <span className={s.pauseSession}>{session.title}</span>}
            </div>
          </div>
        ) : (
          <div className={s.pauseWorld}>
            <div className={s.pauseWorldInfo}>
              <Tape tone="paper" size="sm">NO WORLD OPEN</Tape>
              <span className={s.pauseSession}>Pick a world to meet its characters.</span>
            </div>
          </div>
        )}
        {cast.length > 0 && (
          <div className={s.pauseCast}>
            <Tape tone="brand" size="sm">{cast.length === 1 ? "WITH" : "CAST"}</Tape>
            <ul>
              {cast.slice(0, 5).map((c) => (
                <li key={c!.id}>
                  <img src={headUrl(c!)} alt="" />
                  <span>{c!.profile.name}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </aside>
    </div>
  );
}
