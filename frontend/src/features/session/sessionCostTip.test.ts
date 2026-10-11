// docs/ai/13 W7: the session cost counter's tooltip says it is reply spend only.
import { describe, expect, it } from "vitest";
import { SESSION_COST_TIP } from "./SessionScreen";

describe("session cost tooltip", () => {
  it("says the counter is reply spend only and points to Settings → Cost", () => {
    expect(SESSION_COST_TIP).toBe("Reply cost only. Planning, checks, summaries and memory count toward the daily cap: see Settings → Cost.");
  });
});
