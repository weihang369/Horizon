// Session audio (C): music director → audio.setMusic by the session's musicPolicy (MUS-01..08), plus session SFX:
// emotion changes (D-56: neutral is silent), first token, falling asleep. Stings duck the music bus in the audio
// engine itself (SFX_DUCKS), so any VS / gong / verdict sting played by the ensemble layer ducks automatically.
import { useEffect, useRef } from "react";
import type { SessionRuntimeView } from "../../client/hooks";
import { client } from "../../client";
import { audio } from "../../audio/engine";
import { emotionMeta } from "../../character/emotionMeta";
import type { Character, DebateState, Emotion, ThemeSong } from "../../contract/types";
import { musicDirector } from "../../engine/musicDirector";
import type { MusicCast, TrackRef } from "../../engine/musicDirector";
import { firstName } from "./sessionContext";

/** System tracks (seed/system-tracks.json; procedural "SKETCH" placeholders, R11). */
export const SYSTEM_TRACKS = {
  main: { url: "placeholder:system/main_theme", label: "Horizon Main Theme" },
  arena: { url: "placeholder:system/arena", label: "Arena" },
  ambient: { url: "placeholder:system/ambient_bed", label: "Ambient Bed" },
} satisfies Record<string, TrackRef>;

const songs = new Map<string, Promise<ThemeSong | null>>();
const songOf = (id: string) => {
  let p = songs.get(id);
  if (!p) {
    p = client.characters.song(id).catch(() => null);
    songs.set(id, p);
  }
  return p;
};

export function themeTrack(c: Character | undefined, song: ThemeSong | null | undefined): TrackRef | null {
  if (!c || !song || song.status !== "ready" || !song.url) return null;
  return { url: song.url, label: `${firstName(c.profile.name)}'s Theme`, characterId: c.id };
}

/** Emotion SFX for a display change (D-56: neutral → none). */
export const emotionSfx = (e: Emotion) => (e === "neutral" ? null : emotionMeta[e].sfx);

const SEEK_JUMP = 30;

export function useSessionAudio(rt: SessionRuntimeView, chars: Record<string, Character>, speakerId: string | undefined): void {
  const session = rt.session;
  const castKey = session?.participants.map((p) => p.characterId).join(",") ?? "";

  // ── Music ──
  const themes = useRef<Record<string, TrackRef | null>>({});
  const current = useRef<{ url: string; since: number } | null>(null);
  const evalRef = useRef<() => void>(() => {});
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  evalRef.current = () => {
    if (!session) return;
    const cast: MusicCast[] = session.participants.map((p) => ({
      characterId: p.characterId,
      name: chars[p.characterId]?.profile.name ?? p.characterId,
      side: p.side ?? null,
      theme: themes.current[p.characterId] ?? null,
    }));
    const verdict = session.state && "verdict" in session.state ? (session.state as DebateState).verdict ?? null : null;
    const now = Date.now();
    const d = musicDirector({ mode: session.mode, policy: session.musicPolicy, cast, speakerId: speakerId ?? null, verdict, system: SYSTEM_TRACKS, current: current.current }, now);
    if (timer.current) clearTimeout(timer.current);
    if (d.heldByDwell && current.current) {
      timer.current = setTimeout(() => evalRef.current(), Math.max(500, 20_000 - (now - current.current.since)));
    }
    const t = d.track;
    if (!t) return;
    if (current.current?.url !== t.url) {
      const first = !current.current;
      current.current = { url: t.url, since: now };
      audio.setMusic(t.url, { label: t.label, crossfadeMs: first ? 1500 : 2000 });
    } else {
      audio.setMusic(t.url, { label: t.label });
    }
  };

  // Preload every cast theme at session open (MUS-08), then decide.
  useEffect(() => {
    if (!castKey) return;
    let alive = true;
    const ids = castKey.split(",");
    void Promise.all(ids.map((id) => songOf(id).then((song) => [id, song] as const))).then((rows) => {
      if (!alive) return;
      for (const [id, song] of rows) themes.current[id] = themeTrack(chars[id], song);
      evalRef.current();
    });
    return () => { alive = false; };
  }, [castKey, chars]);

  const verdictKey = session?.state && "verdict" in session.state && (session.state as DebateState).verdict ? "v" : "";
  useEffect(() => {
    evalRef.current();
  }, [session?.musicPolicy, session?.mode, speakerId, verdictKey]);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  // ── SFX ──
  const prevEmo = useRef<Record<string, Emotion> | null>(null);
  const prevSeq = useRef(0);
  const prevAsleep = useRef<Record<string, boolean>>({});
  const firstTokenFor = useRef<string | null>(null);
  const lastSfxAt = useRef(0);
  const lastSeq = rt.runtime?.lastSeq ?? 0;

  useEffect(() => {
    const emo: Record<string, Emotion> = {};
    for (const p of rt.participants) emo[p.characterId] = p.displayEmotion;
    const jumped = Math.abs(lastSeq - prevSeq.current) > SEEK_JUMP || lastSeq < prevSeq.current;
    prevSeq.current = lastSeq;
    const prev = prevEmo.current;
    prevEmo.current = emo;
    if (!prev || jumped) return;
    // One emotion sting at a time, the speaker first (listener reactions are visual-only).
    const order = [...rt.participants].sort((a, b) => (a.characterId === speakerId ? -1 : b.characterId === speakerId ? 1 : 0));
    for (const p of order) {
      const was = prev[p.characterId];
      if (!was || was === p.displayEmotion) continue;
      if (p.characterId !== speakerId && rt.participants.length > 1) continue;
      const sfx = emotionSfx(p.displayEmotion);
      const now = performance.now();
      if (sfx && now - lastSfxAt.current > 250) {
        lastSfxAt.current = now;
        audio.playSfx(sfx);
      }
      break;
    }
  }, [rt.participants, lastSeq, speakerId]);

  // Falling asleep → snore (exhausted VFX is the PortraitCard's).
  useEffect(() => {
    for (const [id, e] of Object.entries(rt.energyById)) {
      const asleep = e.state === "exhausted";
      if (asleep && prevAsleep.current[id] === false) audio.playSfx("energy_snore");
      prevAsleep.current[id] = asleep;
    }
  }, [rt.energyById]);

  // First token of a turn.
  const streaming = rt.streamingId ? rt.messages[rt.streamingId] : undefined;
  const hasText = !!streaming?.content;
  useEffect(() => {
    if (!streaming || !hasText || firstTokenFor.current === streaming.id) return;
    firstTokenFor.current = streaming.id;
    audio.playSfx("ui_first_token");
  }, [streaming, hasText]);
}
