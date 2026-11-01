// A character read outside demo mode settles energy like the backend's `read_energy` (audit F-05): `current`, `asOf`
// and `state` describe the same moment, instead of a `state` from now beside a `current` from the last spend.
import { beforeAll, expect, it } from "vitest";
import { ManualClock } from "../engine/clock";
import type { Dataset } from "./db/dataset";
import { loadSeedDataset } from "./db/loadSeed";
import { MockClient } from "./MockClient";

let seed: Dataset;
beforeAll(async () => {
  seed = await loadSeedDataset();
});

it("a read outside demo mode returns the regenerated energy, as of the read", async () => {
  const clock = new ManualClock();
  const m = new MockClient({ storage: null, dataset: seed, clock, scenario: "image_fail_partial" }); // a key is set
  await m.ready;
  expect((await m.settings.get()).demoMode).toBe(false);
  const low = Object.values(seed.characters).find((c) => !c.deletedAt && c.energy.regenPerHour > 0 && c.energy.current < c.energy.max - 10)!;
  const before = (await m.characters.get(low.id)).energy;
  clock.advance(3600_000);
  const after = (await m.characters.get(low.id)).energy;
  const expected = Math.min(low.energy.max, before.current + low.energy.regenPerHour);
  expect(after.current).toBeGreaterThan(before.current);
  expect(Math.abs(after.current - expected)).toBeLessThanOrEqual(1);   // the wire floors `current`
  expect(after.asOf).toBe(new Date(clock.wallNow()).toISOString());
});
