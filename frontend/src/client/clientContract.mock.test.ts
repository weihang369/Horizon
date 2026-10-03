// HorizonClient contract on the MockClient: the portable suite through a ManualClock harness, plus mock-only checks.
// The M1b HttpClient adds its own harness (backend /_test/* routes) and runs the same portable suite. Owner: EE.
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
    reset: () => mock.dev.resetDemoData(),
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

  it("demo speed ×4 compresses mock time", async () => {
    const h = await mockHarness({ speed: 4 });
    await h.setKey();
    const s = await h.client.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedAmara"] });
    await h.advance(1500);
    expect(chars(await h.client.sessions.messages(s.session.id))[0]?.status).toBe("complete");
  });

  it("wizard portrait candidates are shadow SVG placeholders", async () => {
    const h = await mockHarness();
    await h.setKey();
    const { character } = await h.client.characters.createDraft("wld_seedMeridian", { seedPrompt: "Sarah, a doctor", intent: "expert" });
    await h.advance(5000);
    await h.client.jobs.start({ characterId: character.id, kind: "portrait_candidates" });
    await h.advance(21000);
    const ch = await h.client.characters.get(character.id);
    expect(ch.appearance.candidates.find((x) => x.status === "ready")?.url.startsWith("data:image/svg+xml")).toBe(true);
  });
});
