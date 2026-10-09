// HorizonClient contract on the MockClient: the portable suite through a ManualClock harness, plus mock-only checks.
// The HttpClient runs the same portable suite through its own harness (backend /_test/* routes). Owner: EE.
import { readFileSync } from "node:fs";
import path from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import type { Message } from "../contract/types";
import type { Dataset } from "../mock/db/dataset";
import { loadSeedDataset } from "../mock/db/loadSeed";
import { MockClient } from "../mock/MockClient";
import { ManualClock } from "../mock/time/Clock";
import type { ContractHarness } from "./clientContract.portable";
import { runPortableContract } from "./clientContract.portable";

// Saturday 11:00 MYT: off-peak, so energy maths are the base rate.
const START = Date.parse("2026-10-03T03:00:00Z");
let seed: Dataset;
beforeAll(async () => {
  seed = await loadSeedDataset();
});

async function mockHarness(opts: { speed?: 1 | 2 | 4 } = {}): Promise<ContractHarness & { mock: MockClient; clock: ManualClock }> {
  const clock = new ManualClock(START);
  const mock = new MockClient({ clock, storage: null, dataset: seed, speed: opts.speed });
  await mock.ready;
  return {
    client: mock,
    mock,
    clock,
    advance: async (ms) => {
      for (let t = 0; t < ms; t += 250) {
        clock.advance(Math.min(250, ms - t));
        await Promise.resolve();
      }
      await new Promise((r) => setTimeout(r, 0));
    },
    setScenario: (id) => mock.dev.setScenario(id),
    reset: () => mock.admin.resetDemo(),
    setKey: async () => { await mock.settings.setKey("sk-or-test-0001"); },
  };
}

runPortableContract("MockClient", () => mockHarness());

const chars = (msgs: Message[]) => msgs.filter((m) => m.author.type === "character");

describe("MockClient only", () => {
  it("the portable suite never imports mock internals", () => {
    const src = readFileSync(path.resolve(__dirname, "clientContract.portable.ts"), "utf8");
    expect(src).not.toMatch(/from\s+["'][^"']*\/mock\//);
    expect(src).not.toMatch(/\._db\b|\.dev\./);
  });

  it("every portable test declares its milestone (no bare it())", () => {
    const src = readFileSync(path.resolve(__dirname, "clientContract.portable.ts"), "utf8");
    expect(src).not.toMatch(/^\s+it\(/m);
    expect(src.match(/^\s+test\("M(1b|[2-6])", /gm)?.length).toBeGreaterThanOrEqual(50);
  });

  it("the mock runs every portable test: nothing is pending", () => {
    const src = readFileSync(path.resolve(__dirname, "clientContract.mock.test.ts"), "utf8");
    expect(src).toMatch(/runPortableContract\("MockClient", \(\) => mockHarness\(\)\);/);
  });

  it("the HTTP run declares M6, the last milestone: nothing is pending there either", () => {
    const src = readFileSync(path.resolve(__dirname, "clientContract.http.test.ts"), "utf8");
    expect(src).toMatch(/runPortableContract\("HttpClient", httpHarness, \{ supports: "M6" \}\);/);
  });

  // Mock-only by design (http-client-parity D1): each checks mock semantics or wiring that the backend does differently.
  it("setKey(sk-or-bad…) is invalid immediately (mock semantics; the backend learns it from a 401)", async () => {
    const { client } = await mockHarness();
    expect((await client.settings.setKey("sk-or-bad-zzz")).openRouterKeyStatus).toBe("invalid");
    expect((await client.settings.setKey("not-a-key")).openRouterKeyStatus).toBe("invalid");
  });

  it("demo speed ×4 compresses mock time (a dev affordance; the backend ignores ?speed)", async () => {
    const h = await mockHarness({ speed: 4 });
    await h.setKey();
    const s = await h.client.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedAmara"] });
    await h.advance(1500);
    expect(chars(await h.client.sessions.messages(s.session.id))[0]?.status).toBe("complete");
  });

  it("wizard portrait candidates are shadow SVG placeholders (the backend sends WebP; bytes are not contract)", async () => {
    const h = await mockHarness();
    await h.setKey();
    const { character } = await h.client.characters.createDraft("wld_seedMeridian", { seedPrompt: "Sarah, a doctor", intent: "expert" });
    await h.advance(5000);
    await h.client.jobs.start({ characterId: character.id, kind: "portrait_candidates" });
    await h.advance(21000);
    const ch = await h.client.characters.get(character.id);
    expect(ch.appearance.candidates.find((x) => x.status === "ready")?.url.startsWith("data:image/svg+xml")).toBe(true);
  });

  it("admin.resetDemo is the dev reset: it resolves, keeps settings and announces mock.reset (dev API wiring)", async () => {
    const h = await mockHarness();
    await h.setKey();
    const seen: string[] = [];
    h.client.onGlobal((e) => seen.push(e.type));
    await h.client.admin.resetDemo();
    expect(seen).toContain("mock.reset");
    expect((await h.client.settings.get()).openRouterKeyStatus).toBe("set");
  });
});
