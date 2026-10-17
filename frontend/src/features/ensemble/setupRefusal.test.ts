// M14 (safety D14, task 4.2): a refused motion or premise answers `POST /sessions` with 451 `content_refused`; the
// setup screen's existing `reportError` shows the server's message as a toast (no overlay, no new UI), and the typed
// text stays in the form (the screen only resets `starting`). Owner: SWE.
import { describe, expect, it } from "vitest";
import { reportError } from "../../app/errors";
import { HttpClient } from "../../client/http/HttpClient";
import { ui } from "../../stores/ui";

const MESSAGE = "The motion (or premise) was declined by the safety check. Try different wording.";

describe("a refused motion at session creation", () => {
  it("rejects with content_refused and shows the server's message as a toast", async () => {
    const fetch = async () => new Response(JSON.stringify({ error: { code: "content_refused", message: MESSAGE, retryable: true } }),
      { status: 451, headers: { "content-type": "application/json" } });
    const client = new HttpClient({ baseUrl: "http://x/api/v1", fetch });
    let caught: unknown;
    try {
      await client.sessions.create({ worldId: "wld_a", mode: "debate", characterIds: ["chr_a", "chr_b"] });
    } catch (e) {
      caught = e;
    }
    const shown = reportError(caught, { context: "Starting a session needs an OpenRouter key." });
    expect(shown.code).toBe("content_refused");
    expect(shown.retryable).toBe(true);
    const st = ui.getState();
    expect(st.toasts.at(-1)?.text).toBe(MESSAGE);
    expect(st.layers).toEqual([]);
  });
});
