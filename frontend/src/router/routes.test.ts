// The hash router's parser (v1 test stage, audit 03-F03): a stray `%` in the address must never throw, because
// parseRoute runs at module load, before the app's error boundary exists.
import { describe, expect, it } from "vitest";
import { formatRoute, parseRoute } from "./routes";
import type { Route } from "./routes";

describe("parseRoute", () => {
  it("keeps a malformed escape as typed instead of throwing", () => {
    expect(() => parseRoute("#/w/100%")).not.toThrow();
    expect(parseRoute("#/w/100%")).toEqual({ name: "hub", worldId: "100%" });
    expect(parseRoute("#/onboarding/%E0")).toEqual({ name: "onboarding", card: 1 });
  });

  it("round-trips ids that need escaping", () => {
    const routes: Route[] = [
      { name: "hub", worldId: "wld a/b", tab: "sessions" },
      { name: "session", worldId: "wld_seedMeridian", sessionId: "ses_seed?x", replay: true },
      { name: "settings", tab: "connection", from: "/w/wld_seedMeridian" },
    ];
    for (const r of routes) expect(parseRoute(`#${formatRoute(r)}`)).toEqual(r);
  });

  it("falls back to the title for an empty hash", () => {
    expect(parseRoute("")).toEqual({ name: "title" });
    expect(parseRoute("#/")).toEqual({ name: "title" });
  });
});
