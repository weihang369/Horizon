// Pure hub logic (S04 + S13): filter grammar in the URL, session filtering/sorting, verdict badges, resume targets.
// Owner: Builder A.
import type { DebateConfig, DebateState, Session, SessionMode, WatchState } from "../../contract/types";
import type { Route } from "../../router";

export type ModeFilter = SessionMode | "all";
export type SortOrder = "recent" | "oldest";
export interface SessionFilter { mode: ModeFilter; characterId: string | null; sort: SortOrder }

const MODES: ModeFilter[] = ["all", "one_on_one", "group", "debate", "watch"];
export const DEFAULT_SESSION_FILTER: SessionFilter = { mode: "all", characterId: null, sort: "recent" };

/** `?filter=` on the Sessions tab: `mode[.characterId][.oldest]`, e.g. "debate", "all.chr_seedMei", "group..oldest". */
export function parseSessionFilter(raw: string | undefined): SessionFilter {
  if (!raw) return DEFAULT_SESSION_FILTER;
  const [m, c, o] = raw.split(".");
  return {
    mode: (MODES as string[]).includes(m) ? (m as ModeFilter) : "all",
    characterId: c ? c : null,
    sort: o === "oldest" ? "oldest" : "recent",
  };
}

export function formatSessionFilter(f: SessionFilter): string | undefined {
  if (f.mode === "all" && !f.characterId && f.sort === "recent") return undefined;
  const parts = [f.mode, f.characterId ?? "", f.sort === "oldest" ? "oldest" : ""];
  while (parts.length > 1 && parts[parts.length - 1] === "") parts.pop();
  return parts.join(".");
}

export const isFiltered = (f: SessionFilter): boolean => f.mode !== "all" || !!f.characterId;

const lastActivity = (s: Session): number => Date.parse(s.lastMessageAt ?? s.updatedAt);

export function filterSessions(list: Session[], f: SessionFilter): Session[] {
  const out = list.filter((s) =>
    (f.mode === "all" || s.mode === f.mode) &&
    (!f.characterId || s.participants.some((p) => p.characterId === f.characterId)));
  out.sort((a, b) => (f.sort === "recent" ? lastActivity(b) - lastActivity(a) : lastActivity(a) - lastActivity(b)));
  return out;
}

export const MODE_LABEL: Record<SessionMode, string> = { one_on_one: "1:1", group: "Group", debate: "Debate", watch: "Watch" };

/** Verdict badge for a debate row (HIST-01 AC2). Null = no badge. */
export function verdictBadge(s: Session): { text: string; tone: "prop" | "opp" | "ink" } | null {
  if (s.mode !== "debate") return null;
  const v = (s.state as DebateState | null)?.verdict;
  if (!v) return s.status === "ended" ? { text: "NO VERDICT", tone: "ink" } : null;
  if (v.strongerCase === "prop") return { text: "STRONGER CASE · PROP", tone: "prop" };
  if (v.strongerCase === "opp") return { text: "STRONGER CASE · OPP", tone: "opp" };
  if (v.decidedBy === "none") return { text: "NO VERDICT", tone: "ink" };
  return { text: "TOO CLOSE TO CALL", tone: "ink" };
}

/** One-line context under a row's title: the motion, the watch premise, or the cast size. */
export function sessionSubtitle(s: Session): string {
  if (s.mode === "debate") return (s.config as DebateConfig | null)?.motion ?? "Debate";
  if (s.mode === "watch") {
    const st = s.state as WatchState | null;
    const premise = (s.config as { premise?: string } | null)?.premise;
    return [premise, st ? `turn ${st.turnsTaken} / ${st.turnLimit}` : null].filter(Boolean).join(" · ");
  }
  return `${s.messageCount} message${s.messageCount === 1 ? "" : "s"}`;
}

/** Where "Resume" goes (HIST-02): ended debate → read-only Verdict; everything else → the session (seed = DemoDock). */
export function resumeRoute(s: Session): Route {
  if (s.mode === "debate" && s.status === "ended") return { name: "verdict", worldId: s.worldId, sessionId: s.id };
  return { name: "session", worldId: s.worldId, sessionId: s.id };
}

export function resumeLabel(s: Session): string {
  if (s.mode === "debate" && s.status === "ended") return "Verdict";
  if (s.isSeed || s.status === "ended") return "Open";
  return "Resume";
}

/** The demo "featured recording" for a world: its seed debate, else a seed group/watch, else any seed session. */
export function featuredRecording(list: Session[]): Session | null {
  const seeds = list.filter((s) => s.isSeed);
  const rank: Record<SessionMode, number> = { debate: 0, group: 1, watch: 2, one_on_one: 3 };
  const sorted = [...seeds].sort((a, b) => rank[a.mode] - rank[b.mode] || lastActivity(b) - lastActivity(a));
  return sorted[0] ?? null;
}

export function featuredCta(s: Session): string {
  return s.mode === "debate" ? "Watch the debate" : s.mode === "watch" ? "Watch the episode" : "Watch the recording";
}
