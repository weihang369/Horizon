// The mock's localStorage snapshot is debounced (500 ms). Reloading or closing the tab inside that window used to drop
// the last change (a setting flipped just before a reload came back old); pagehide now writes the pending one at once.
import { afterEach, beforeAll, expect, it, vi } from "vitest";
import type { Dataset } from "./db/dataset";
import { loadSeedDataset } from "./db/loadSeed";
import { SNAPSHOT_KEY } from "./db/persist";
import type { KV } from "./db/persist";
import { MockClient } from "./MockClient";

let seed: Dataset;
beforeAll(async () => {
  seed = await loadSeedDataset();
});
afterEach(() => vi.unstubAllGlobals());

it("pagehide writes a pending snapshot at once, so a reload keeps the last change", async () => {
  const win = new EventTarget();
  vi.stubGlobal("window", win);
  const kv = new Map<string, string>();
  const storage: KV = { getItem: (k) => kv.get(k) ?? null, setItem: (k, v) => void kv.set(k, v), removeItem: (k) => void kv.delete(k) };
  const reopen = async () => {
    const m = new MockClient({ storage, dataset: seed });
    await m.ready;
    return (await m.settings.get()).chat.responderDefault;
  };

  const tab = new MockClient({ storage, dataset: seed });
  await tab.ready;
  await tab.settings.update({ chat: { responderDefault: "mentioned" } });
  const saved = () => (JSON.parse(kv.get(SNAPSHOT_KEY) ?? "null") as { data: Dataset } | null)?.data.settings.chat.responderDefault;
  expect(saved()).not.toBe("mentioned"); // still inside the 500 ms debounce
  win.dispatchEvent(new Event("pagehide"));
  expect(await reopen()).toBe("mentioned");
});
