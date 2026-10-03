// O24 Portrait menu (MULTI-17, D-50) — Builder D. One gesture, one meaning: click / right-click / Enter / Shift+F10
// on any stage portrait opens this skewed 200 px menu with only the actions valid for the mode:
// Speak next (group, watch) · Set face ▸ (MANUAL only) · Mute / Unmute (group, watch) · View profile.
// Replays are read-only: only View profile. ↑↓ / Home / End move, Enter picks, Esc closes (popover-first, R4).
import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { client } from "../../client";
import type { Emotion } from "../../contract/types";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { run } from "../../app/errors";
import { emotionMeta, EMOTION_ORDER, PortraitCard } from "../../character";
import { navigate } from "../../router";
import { PaletteScope } from "../../theme";
import { cx } from "../../ui";
import { firstName, useCharMap, useSlot } from "./shared";
import s from "./Overlays.module.css";

interface Item { id: string; label: string; hint?: string; run: () => void; checked?: boolean }

export function PortraitMenu({ sessionId, characterId, close }: OverlayComponentProps<"O24">) {
  const slot = useSlot(sessionId);
  const chars = useCharMap();
  const c = chars[characterId];
  const rt = slot?.runtime;
  const session = rt?.session;
  const p = session?.participants.find((x) => x.characterId === characterId);
  const mode = session?.mode;
  const replay = !!slot?.replay;
  const live = !replay && session?.status !== "ended";
  const manual = session?.emotionMode === "user";
  const [faces, setFaces] = useState(false);
  const current: Emotion = rt?.displayEmotion[characterId] ?? p?.currentEmotion ?? "neutral";

  const items: Item[] = [];
  if (faces) {
    items.push({ id: "back", label: "◂ Back", run: () => setFaces(false) });
    for (const e of EMOTION_ORDER) {
      items.push({
        id: `face:${e}`,
        label: `${emotionMeta[e].icon}  ${emotionMeta[e].label}`,
        hint: String(emotionMeta[e].hotkey),
        checked: e === current,
        run: () => {
          void run(() => client.chat.setEmotion(sessionId, characterId, e));
          close();
        },
      });
    }
  } else {
    if (live && (mode === "group" || mode === "watch")) {
      items.push({
        id: "speak",
        label: "Speak next",
        hint: "▸",
        run: () => {
          void run(() => client.chat.nextSpeaker(sessionId, characterId));
          close();
        },
      });
    }
    if (live && manual) items.push({ id: "face", label: "Set face", hint: "▸", run: () => setFaces(true) });
    if (live && (mode === "group" || mode === "watch")) {
      const muted = !!p?.mutedByUser;
      items.push({
        id: "mute",
        label: muted ? "Unmute" : "Mute",
        hint: muted ? "speaks again" : "skips turns",
        run: () => {
          void run(() => client.chat.muteParticipant(sessionId, characterId, !muted));
          close();
        },
      });
    }
    items.push({
      id: "profile",
      label: "View profile",
      hint: "↗",
      run: () => {
        close();
        if (session) navigate({ name: "profile", worldId: session.worldId, characterId });
      },
    });
  }

  const [active, setActive] = useState(0);
  const list = useRef<HTMLUListElement>(null);
  useEffect(() => {
    setActive(faces ? Math.max(1, EMOTION_ORDER.indexOf(current) + 1) : 0);
  }, [faces]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    list.current?.querySelectorAll<HTMLButtonElement>("button")[active]?.focus({ preventScroll: true });
  }, [active, faces]);

  const onKey = (e: KeyboardEvent) => {
    const n = items.length;
    if (e.key === "ArrowDown") setActive((a) => (a + 1) % n);
    else if (e.key === "ArrowUp") setActive((a) => (a - 1 + n) % n);
    else if (e.key === "Home") setActive(0);
    else if (e.key === "End") setActive(n - 1);
    else if (e.key === "ArrowLeft" && faces) setFaces(false);
    else if (e.key === "ArrowRight" && !faces && items[active]?.id === "face") setFaces(true);
    else if (e.key === "Tab") return close();
    else return;
    e.preventDefault();
  };

  if (!c) return null;
  return (
    <PaletteScope paletteId={c.paletteId} className={s.pmenu}>
      <div className={s.pmHead}>
        <PortraitCard character={c} emotion={current} size="head" width={40} />
        <div className={s.pmWho}>
          <span className={s.pmName}>{firstName(c)}</span>
          <span className={s.pmSub}>{faces ? "Set face · MANUAL" : p?.mutedByUser ? "Muted" : emotionMeta[current].label}</span>
        </div>
      </div>
      <ul ref={list} role="menu" aria-label={`${c.profile.name} actions`} className={s.pmList} onKeyDown={onKey}>
        {items.map((it, i) => (
          <li key={it.id} role="none">
            <button
              type="button"
              role={it.checked !== undefined ? "menuitemradio" : "menuitem"}
              aria-checked={it.checked}
              tabIndex={i === active ? 0 : -1}
              className={cx(s.pmItem, it.checked && s.pmChecked)}
              onPointerEnter={() => setActive(i)}
              onClick={it.run}
            >
              <span>{it.label}</span>
              {it.hint && <span className={s.pmHint}>{it.hint}</span>}
            </button>
          </li>
        ))}
      </ul>
      {replay && <p className={s.pmNote}>Replay · read-only</p>}
    </PaletteScope>
  );
}
