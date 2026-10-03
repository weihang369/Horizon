// HorizonClient contract over HTTP: the portable suite against a real test-mode backend (`npm run test:http`).
// The backend implements milestone M1b, so later tests are listed as `[pending Mx]` (client-contract spec).
// Each test starts from a factory reset (fresh seed + _mock overlays) with the clock frozen at the mock harness's START.
// Owner: SWE.
import { EventSource } from "eventsource";
import { inject } from "vitest";
import type { ContractHarness } from "./clientContract.portable";
import { runPortableContract } from "./clientContract.portable";
import { HttpClient } from "./http/HttpClient";
import type { EventSourceCtor } from "./http/sse";

const START = "2026-10-03T03:00:00.000Z";
const base = inject("horizonBaseUrl");

async function post(path: string, body: unknown): Promise<Response> {
  const r = await fetch(`${base}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok && r.status !== 422) throw new Error(`${path}: ${r.status} ${await r.text()}`);
  return r;
}

async function httpHarness(): Promise<ContractHarness> {
  await post("/admin/factory-reset", { confirm: "DELETE EVERYTHING" });
  await post("/_test/clock", { freezeAt: START });
  const client = new HttpClient({ baseUrl: base, EventSource: EventSource as unknown as EventSourceCtor });
  return {
    client,
    advance: async (ms) => {
      await post("/_test/clock", { advanceMs: ms });
    },
    setScenario: async (id) => {
      const r = await post("/_test/scenario", { id });
      if (r.status === 422) throw new Error(`scenario ${id} is not available on the backend yet`);
    },
    reset: () => client.admin.resetDemo(),
    setKey: () => Promise.reject(new Error("pending M2: key handling")),
    dispose: () => client.dispose(),
  };
}

runPortableContract("HttpClient", httpHarness, { supports: "M1b" });
