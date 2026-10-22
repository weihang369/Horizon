// The Pipeline's steps for one turn (Insight, U-57).
import type { TurnTrace } from "../../contract/types";

const PLAN_STEPS = ["state", "ask", "decide", "route"];
const PLAN_PURPOSES = new Set(["turn_plan", "debate_plan", "follow_plan", "route"]);

/** U-57: the same path for the same kind of turn. A plan made ahead (or in another task) records only the search's
 * steps, and a search started outside the plan graph has no "deep" step; both are put back, so every planned turn shows
 * state → ask → decide → route, and every search starts with deep. */
export function turnPath(trace?: TurnTrace): string[] {
  const raw = trace?.graph?.path ?? [];
  if (!raw.length) return [];
  const planned = trace?.system1?.questions.some((r) => PLAN_PURPOSES.has(r.purpose)) ?? false;
  let path = planned && !raw.includes("state") ? [...PLAN_STEPS, ...raw] : [...raw];
  if (path.some((p) => p === "gather" || p === "search" || p === "recall") && !path.includes("deep")) {
    const at = path.indexOf("route") + 1;
    path = [...path.slice(0, at), "deep", ...path.slice(at)];
  }
  return path.filter((p, i) => path.indexOf(p) === i);
}
