// MUS-01..08 as one pure function: (session context, now) → which track should play.
// The audio engine only ever gets the result (setMusic(url)); all rules live here and are unit-tested.
import type { MusicPolicy, SessionMode, Side, Verdict } from "../contract/types";

export const FOLLOW_DWELL_MS = 20_000;

export interface TrackRef { url: string; label: string; characterId?: string }

export interface MusicCast {
  characterId: string;
  name: string;
  side?: Side | null;
  /** The character's theme, if it has one (status ready). */
  theme?: TrackRef | null;
}

export interface MusicInput {
  mode: SessionMode | "hub" | "profile";
  policy?: MusicPolicy;
  cast: MusicCast[];
  speakerId?: string | null;
  verdict?: Verdict | null;
  /** System tracks. */
  system: { main?: TrackRef; arena?: TrackRef; ambient?: TrackRef };
  /** What is playing now and since when (epoch ms). */
  current?: { url: string; since: number } | null;
}

export interface MusicDecision {
  track: TrackRef | null;
  /** True when a change was held back by the follow-speaker dwell (re-evaluate later). */
  heldByDwell?: boolean;
}

function ambientOr(input: MusicInput): TrackRef | null {
  return input.system.ambient ?? null;
}

/** Theme of the highest-scoring debater on the stronger side (else the first-listed debater on that side). */
export function verdictWinnerTheme(cast: MusicCast[], verdict: Verdict): TrackRef | null {
  if (verdict.strongerCase !== "prop" && verdict.strongerCase !== "opp") return null;
  const side = verdict.strongerCase;
  const onSide = cast.filter((c) => c.side === side);
  if (!onSide.length) return null;
  let best = onSide[0];
  if (verdict.scoresBy === "debater" && verdict.scores?.length) {
    let bestScore = -Infinity;
    for (const c of onSide) {
      const total = verdict.scores.filter((s) => s.subjectId === c.characterId).reduce((a, s) => a + s.value, 0);
      if (total > bestScore) {
        bestScore = total;
        best = c;
      }
    }
  }
  return best.theme ?? null;
}

export function musicDirector(input: MusicInput, nowMs: number): MusicDecision {
  const { mode, cast } = input;

  if (mode === "hub") return { track: input.system.main ?? null };

  if (mode === "profile" || mode === "one_on_one" || input.policy === "character_theme") {
    const c = cast[0];
    return { track: c?.theme ?? ambientOr(input) };
  }

  if (mode === "debate" || input.policy === "arena") {
    if (input.verdict) {
      const winner = verdictWinnerTheme(cast, input.verdict);
      if (winner) return { track: winner };
    }
    return { track: input.system.arena ?? ambientOr(input) };
  }

  if (input.policy === "scene_bed") return { track: ambientOr(input) };

  // follow_speaker (group and watch default)
  const currentUrl = input.current?.url;
  const speaker = cast.find((c) => c.characterId === input.speakerId);
  if (!currentUrl) {
    const first = speaker?.theme ?? cast.find((c) => c.theme)?.theme ?? null;
    return { track: first ?? ambientOr(input) };
  }
  const keep: TrackRef = cast.map((c) => c.theme).find((t) => t?.url === currentUrl)
    ?? [input.system.ambient, input.system.arena, input.system.main].find((t) => t?.url === currentUrl)
    ?? { url: currentUrl, label: "" };
  if (!speaker?.theme || speaker.theme.url === currentUrl) return { track: keep };
  const since = input.current?.since ?? 0;
  if (nowMs - since < FOLLOW_DWELL_MS) return { track: keep, heldByDwell: true };
  return { track: speaker.theme };
}
