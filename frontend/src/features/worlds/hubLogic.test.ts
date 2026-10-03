import { describe, expect, it } from "vitest";
import type { Session } from "../../contract/types";
import {
  DEFAULT_SESSION_FILTER, featuredRecording, filterSessions, formatSessionFilter, parseSessionFilter, resumeLabel,
  resumeRoute, verdictBadge,
} from "./hubLogic";

const ses = (p: Partial<Session> & Pick<Session, "id" | "mode">): Session => ({
  worldId: "w", title: p.id, titleIsCustom: false, status: "paused", participants: [], emotionMode: "llm",
  musicPolicy: "follow_speaker", readableMode: false, config: null, state: null, isSeed: false, costUsd: 0, messageCount: 3,
  createdAt: "2026-09-01T00:00:00Z", updatedAt: "2026-09-01T00:00:00Z", ...p,
});

describe("session filter grammar", () => {
  it("round-trips", () => {
    for (const f of [
      { mode: "debate", characterId: null, sort: "recent" },
      { mode: "all", characterId: "chr_x", sort: "recent" },
      { mode: "group", characterId: null, sort: "oldest" },
      { mode: "watch", characterId: "chr_y", sort: "oldest" },
    ] as const) {
      expect(parseSessionFilter(formatSessionFilter(f))).toEqual(f);
    }
  });
  it("default formats to nothing and junk parses to default", () => {
    expect(formatSessionFilter(DEFAULT_SESSION_FILTER)).toBeUndefined();
    expect(parseSessionFilter("nonsense")).toEqual(DEFAULT_SESSION_FILTER);
  });
});

describe("filterSessions", () => {
  const list = [
    ses({ id: "a", mode: "debate", lastMessageAt: "2026-09-03T00:00:00Z", participants: [{ characterId: "m", role: "debater", currentEmotion: "neutral", mutedByUser: false }] }),
    ses({ id: "b", mode: "group", lastMessageAt: "2026-09-05T00:00:00Z" }),
    ses({ id: "c", mode: "debate", lastMessageAt: "2026-09-01T00:00:00Z" }),
  ];
  it("filters by mode and character, sorts by most recent", () => {
    expect(filterSessions(list, DEFAULT_SESSION_FILTER).map((s) => s.id)).toEqual(["b", "a", "c"]);
    expect(filterSessions(list, { ...DEFAULT_SESSION_FILTER, mode: "debate" }).map((s) => s.id)).toEqual(["a", "c"]);
    expect(filterSessions(list, { ...DEFAULT_SESSION_FILTER, characterId: "m" }).map((s) => s.id)).toEqual(["a"]);
    expect(filterSessions(list, { ...DEFAULT_SESSION_FILTER, sort: "oldest" }).map((s) => s.id)).toEqual(["c", "a", "b"]);
  });
});

describe("rows", () => {
  it("ended debates resume into their verdict (HIST-02)", () => {
    const d = ses({ id: "d", mode: "debate", status: "ended" });
    expect(resumeRoute(d)).toEqual({ name: "verdict", worldId: "w", sessionId: "d" });
    expect(resumeLabel(d)).toBe("Verdict");
    expect(resumeRoute(ses({ id: "e", mode: "group" }))).toEqual({ name: "session", worldId: "w", sessionId: "e" });
  });
  it("labels verdicts", () => {
    const base = { decidedBy: "arbiter" as const, summary: [] };
    expect(verdictBadge(ses({ id: "v", mode: "debate", state: { phase: "ended", round: 3, iteration: 0, verdict: { ...base, strongerCase: "prop" } } }))?.text).toBe("STRONGER CASE · PROP");
    expect(verdictBadge(ses({ id: "v", mode: "debate", state: { phase: "ended", round: 3, iteration: 0, verdict: { ...base, strongerCase: null } } }))?.text).toBe("TOO CLOSE TO CALL");
    expect(verdictBadge(ses({ id: "g", mode: "group" }))).toBeNull();
  });
  it("features the seed debate first", () => {
    const list = [ses({ id: "g", mode: "group", isSeed: true }), ses({ id: "d", mode: "debate", isSeed: true }), ses({ id: "x", mode: "debate" })];
    expect(featuredRecording(list)?.id).toBe("d");
    expect(featuredRecording([ses({ id: "x", mode: "debate" })])).toBeNull();
  });
});
