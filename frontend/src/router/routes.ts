// Routes (README §3.1, UXA §2.1): a typed union ⇄ hash paths. Pure. Owner: EE.
//   #/                                   title          #/onboarding/:card     onboarding
//   #/worlds                             worlds         #/w/:wid?tab=&filter=  hub (+ S13 Sessions tab)
//   #/w/:wid/c/:cid?tab=                 profile        #/w/:wid/create/:step  wizard (new)
//   #/w/:wid/c/:cid/edit/:step           wizard (edit)  #/w/:wid/c/:cid/draft/:step  wizard (resume draft)
//   #/w/:wid/setup/:step?mode=&cast=     setup          #/w/:wid/s/:sid?replay=1&t=<seq>  session
//   #/w/:wid/s/:sid/verdict              verdict        #/settings/:tab?from=  settings
//   #/dev/kit                            Kit Gallery
import type { CreationStep } from "../contract/types";
import { CREATION_STEPS } from "../contract/types";

export type ProfileTab = "profile" | "gallery" | "theme" | "sessions" | "memory" | "knowledge";
export type SettingsTab = "connection" | "audio" | "chat" | "display" | "models" | "cost" | "data" | "about";
export const PROFILE_TABS: ProfileTab[] = ["profile", "gallery", "theme", "sessions", "memory", "knowledge"];
export const SETTINGS_TABS: SettingsTab[] = ["connection", "audio", "chat", "display", "models", "cost", "data", "about"];

export type Route =
  | { name: "title" }
  | { name: "onboarding"; card?: number }
  | { name: "worlds" }
  | { name: "hub"; worldId: string; tab?: "roster" | "sessions"; filter?: string }
  | { name: "profile"; worldId: string; characterId: string; tab?: ProfileTab }
  | { name: "wizard"; worldId: string; characterId?: string; step?: CreationStep; edit?: boolean }
  | { name: "setup"; worldId: string; step?: "mode" | "cast" | "config"; mode?: "group" | "debate" | "watch"; cast?: string[] }
  | { name: "session"; worldId: string; sessionId: string; replay?: boolean; t?: number }
  | { name: "verdict"; worldId: string; sessionId: string }
  | { name: "settings"; tab?: SettingsTab; from?: string }
  | { name: "dev"; page: "kit" };

export type RouteName = Route["name"];

const enc = encodeURIComponent;
const oneOf = <T extends string>(v: string | null | undefined, list: readonly T[]): T | undefined =>
  v && (list as readonly string[]).includes(v) ? (v as T) : undefined;

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== false && v !== "")
    .map(([k, v]) => `${k}=${v === true ? "1" : enc(String(v))}`);
  return parts.length ? `?${parts.join("&")}` : "";
}

export function formatRoute(r: Route): string {
  switch (r.name) {
    case "title": return "/";
    case "onboarding": return r.card ? `/onboarding/${r.card}` : "/onboarding";
    case "worlds": return "/worlds";
    case "hub": return `/w/${enc(r.worldId)}${qs({ tab: r.tab, filter: r.filter })}`;
    case "profile": return `/w/${enc(r.worldId)}/c/${enc(r.characterId)}${qs({ tab: r.tab })}`;
    case "wizard":
      if (!r.characterId) return `/w/${enc(r.worldId)}/create/${r.step ?? "seed"}`;
      return `/w/${enc(r.worldId)}/c/${enc(r.characterId)}/${r.edit ? "edit" : "draft"}/${r.step ?? "profile"}`;
    case "setup": return `/w/${enc(r.worldId)}/setup/${r.step ?? "mode"}${qs({ mode: r.mode, cast: r.cast?.join(",") })}`;
    case "session": return `/w/${enc(r.worldId)}/s/${enc(r.sessionId)}${qs({ replay: r.replay, t: r.t })}`;
    case "verdict": return `/w/${enc(r.worldId)}/s/${enc(r.sessionId)}/verdict`;
    case "settings": return `/settings${r.tab ? `/${r.tab}` : ""}${qs({ from: r.from })}`;
    case "dev": return `/dev/${r.page}`;
  }
}

/** Parse a hash ("#/w/x?tab=sessions") or path. Unknown paths fall back to the title. */
export function parseRoute(hash: string): Route {
  const raw = hash.replace(/^#/, "") || "/";
  const [path, query = ""] = raw.split("?");
  const q = new URLSearchParams(query);
  const seg = path.split("/").filter(Boolean).map(decodeURIComponent);
  const step = (v?: string) => oneOf(v, CREATION_STEPS);
  if (seg.length === 0) return { name: "title" };
  if (seg[0] === "onboarding") return { name: "onboarding", ...(seg[1] ? { card: Number(seg[1]) || 1 } : {}) };
  if (seg[0] === "worlds") return { name: "worlds" };
  if (seg[0] === "settings") return { name: "settings", ...(oneOf(seg[1], SETTINGS_TABS) ? { tab: seg[1] as SettingsTab } : {}), ...(q.get("from") ? { from: q.get("from")! } : {}) };
  if (seg[0] === "dev" && seg[1] === "kit") return { name: "dev", page: "kit" };
  if (seg[0] === "w" && seg[1]) {
    const worldId = seg[1];
    if (seg.length === 2) {
      return {
        name: "hub", worldId,
        ...(oneOf(q.get("tab"), ["roster", "sessions"] as const) ? { tab: q.get("tab") as "roster" | "sessions" } : {}),
        ...(q.get("filter") ? { filter: q.get("filter")! } : {}),
      };
    }
    if (seg[2] === "create") return { name: "wizard", worldId, step: step(seg[3]) ?? "seed" };
    if (seg[2] === "setup") {
      const st = oneOf(seg[3], ["mode", "cast", "config"] as const);
      const mode = oneOf(q.get("mode"), ["group", "debate", "watch"] as const);
      const cast = q.get("cast")?.split(",").filter(Boolean);
      return { name: "setup", worldId, ...(st ? { step: st } : {}), ...(mode ? { mode } : {}), ...(cast?.length ? { cast } : {}) };
    }
    if (seg[2] === "c" && seg[3]) {
      const characterId = seg[3];
      if (seg[4] === "edit" || seg[4] === "draft") return { name: "wizard", worldId, characterId, step: step(seg[5]) ?? "profile", ...(seg[4] === "edit" ? { edit: true } : {}) };
      const tab = oneOf(q.get("tab"), PROFILE_TABS);
      return { name: "profile", worldId, characterId, ...(tab ? { tab } : {}) };
    }
    if (seg[2] === "s" && seg[3]) {
      if (seg[4] === "verdict") return { name: "verdict", worldId, sessionId: seg[3] };
      const t = q.get("t");
      return { name: "session", worldId, sessionId: seg[3], ...(q.get("replay") === "1" ? { replay: true } : {}), ...(t && !Number.isNaN(Number(t)) ? { t: Number(t) } : {}) };
    }
    return { name: "hub", worldId };
  }
  return { name: "title" };
}

/** The logical parent when in-app history is empty (UXA §2.1 Back). */
export function parentOf(r: Route): Route {
  switch (r.name) {
    case "title": case "onboarding": return { name: "title" };
    case "worlds": return { name: "title" };
    case "hub": return { name: "worlds" };
    case "profile": case "wizard": case "setup": return { name: "hub", worldId: r.worldId };
    case "session": return r.replay ? { name: "hub", worldId: r.worldId, tab: "sessions" } : { name: "hub", worldId: r.worldId };
    case "verdict": return { name: "hub", worldId: r.worldId, tab: "sessions" };
    case "settings": return r.from ? parseRoute(r.from) : { name: "worlds" };
    case "dev": return { name: "worlds" };
  }
}

export const sameRoute = (a: Route, b: Route): boolean => formatRoute(a) === formatRoute(b);
