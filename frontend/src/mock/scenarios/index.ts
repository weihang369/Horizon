// Mock State Switcher scenarios (APP-08 AC1) as data (EE paper §2.3). Owner: EE.
// A scenario = settings patch + dataset overlay + faults + timing patch. Overlay scenarios re-seed the DB
// (and emit mock.reset); the others patch the running mock in place so they land on the current screen.
import type { AppSettings, ErrorCode } from "../../contract/types";
import type { DeepPartial } from "../../client/HorizonClient";
import type { PricePeriod } from "../../domain/rushHour";
import type { Dataset } from "../db/dataset";
import type { TimingConfig } from "../timing.config";

export type ScenarioId =
  | "default" | "no_key" | "invalid_key" | "rate_limited" | "out_of_credits" | "network_down" | "content_refused"
  | "daily_cap" | "character_exhausted" | "rush_hour" | "image_fail_all" | "image_fail_partial" | "song_fails"
  | "stream_cut" | "empty_world" | "no_worlds" | "slow_stream" | "reactions_late" | "emotion_late";

export interface CommandFault {
  code: ErrorCode;
  /** Fail this many times, then succeed (undefined = until reset). */
  times?: number;
  /** Also fail queries (network down). Default: live actions only. */
  queries?: boolean;
  retryAfterSec?: number;
}

export interface Faults {
  command?: CommandFault;
  /** Next character turn(s): "cut" = error(network) after N tokens + turn.end(interrupted); "refuse" = content_refused. */
  stream?: { kind: "cut"; afterTokens: number; times?: number } | { kind: "refuse"; times?: number };
  /** Generation jobs. */
  job?: "all" | "partial" | "song";
}

export interface Scenario {
  id: ScenarioId;
  label: string;
  group: "Key & account" | "Errors" | "Budget & energy" | "Generation" | "Streaming" | "Data";
  hint: string;
  settingsPatch?: DeepPartial<AppSettings>;
  /** Re-seeds the DB, then mutates the fresh dataset. */
  overlay?: (ds: Dataset) => void;
  faults?: Faults;
  timingPatch?: Partial<TimingConfig>;
  pricePeriod?: PricePeriod;
}

const KEY_SET: DeepPartial<AppSettings> = { openRouterKeyStatus: "set", demoMode: false };

export const SCENARIOS: Scenario[] = [
  { id: "default", label: "Default", group: "Key & account", hint: "Shipped fixtures, no faults." },
  { id: "no_key", label: "No key (demo mode)", group: "Key & account", hint: "Recordings play; live actions open O05.", settingsPatch: { openRouterKeyStatus: "missing", demoMode: true } },
  { id: "invalid_key", label: "Invalid key", group: "Key & account", hint: "Live actions reject with invalid_key.", settingsPatch: { openRouterKeyStatus: "invalid", demoMode: true } },
  { id: "rate_limited", label: "Rate limited", group: "Errors", hint: "Next live action fails once (retry in 12 s).", settingsPatch: KEY_SET, faults: { command: { code: "rate_limited", times: 1, retryAfterSec: 12 } } },
  { id: "out_of_credits", label: "Out of credits", group: "Errors", hint: "Live actions reject with insufficient_credits.", settingsPatch: KEY_SET, faults: { command: { code: "insufficient_credits" } } },
  { id: "network_down", label: "Network down", group: "Errors", hint: "Every call rejects with network.", faults: { command: { code: "network", queries: true } } },
  { id: "content_refused", label: "Content refused", group: "Errors", hint: "Next reply is refused (content_refused).", settingsPatch: KEY_SET, faults: { stream: { kind: "refuse", times: 1 } } },
  { id: "daily_cap", label: "Daily cap reached", group: "Budget & energy", hint: "Spend = cap: sessions pause (daily_budget), generation blocked.", settingsPatch: { ...KEY_SET, spentTodayUsd: 1.0 } },
  {
    id: "character_exhausted", label: "Character exhausted", group: "Budget & energy", hint: "Takeshi at 0 ⚡ (seed variant).", settingsPatch: KEY_SET,
    overlay: (ds) => {
      const v = ds.variants.exhausted_takeshi;
      for (const p of v?.characterPatches ?? []) {
        const c = ds.characters[p.characterId];
        if (c && p.energy) c.energy = { ...c.energy, current: p.energy.current, state: p.energy.state, fullAt: undefined };
      }
    },
  },
  { id: "rush_hour", label: "Rush hour", group: "Budget & energy", hint: "Peak pricing: replies cost 2× ⚡.", settingsPatch: KEY_SET, pricePeriod: "peak" },
  { id: "image_fail_all", label: "Image generation fails (all)", group: "Generation", hint: "Every image task fails.", settingsPatch: KEY_SET, faults: { job: "all" } },
  { id: "image_fail_partial", label: "Image generation fails (partial)", group: "Generation", hint: "Task 2 fails at 60 %; Retry succeeds.", settingsPatch: KEY_SET, faults: { job: "partial" } },
  { id: "song_fails", label: "Song fails", group: "Generation", hint: "Theme song task fails.", settingsPatch: KEY_SET, faults: { job: "song" } },
  { id: "stream_cut", label: "Stream cut mid-reply", group: "Streaming", hint: "Next reply cuts after ~24 tokens.", settingsPatch: KEY_SET, faults: { stream: { kind: "cut", afterTokens: 24, times: 1 } } },
  { id: "slow_stream", label: "Slow stream", group: "Streaming", hint: "4 s to first token, 8 tok/s.", settingsPatch: KEY_SET, timingPatch: { firstTokenMs: 4000, tokensPerSec: 8 } },
  { id: "reactions_late", label: "Reactions late or missing", group: "Streaming", hint: "30 % react, 2.5–4 s late.", settingsPatch: KEY_SET, timingPatch: { reactionChance: 0.3, reactionDelayMs: [2500, 4000] } },
  { id: "emotion_late", label: "Emotion arrives late", group: "Streaming", hint: "Every emotion lands after the 800 ms hold.", settingsPatch: KEY_SET, timingPatch: { emotionTiming: { before: 0, early: 0, late: 1 } } },
  {
    id: "empty_world", label: "Empty world", group: "Data", hint: "Both worlds exist with no characters or sessions.",
    overlay: (ds) => {
      ds.characters = {};
      ds.sessions = {};
      ds.memory = {};
      ds.knowledge = {};
      ds.jobs = {};
      for (const w of Object.values(ds.worlds)) w.characterCount = 0;
    },
  },
  {
    id: "no_worlds", label: "No worlds", group: "Data", hint: "Nothing at all: World Select empty state.",
    overlay: (ds) => {
      ds.worlds = {};
      ds.characters = {};
      ds.sessions = {};
      ds.memory = {};
      ds.knowledge = {};
      ds.jobs = {};
    },
  },
];

export const SCENARIO_BY_ID = Object.fromEntries(SCENARIOS.map((s) => [s.id, s])) as Record<ScenarioId, Scenario>;
export const isScenarioId = (x: string | null | undefined): x is ScenarioId => !!x && x in SCENARIO_BY_ID;
