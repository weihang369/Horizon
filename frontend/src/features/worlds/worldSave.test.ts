// The World editor's save flow with a fake client (worlds "The world editor uploads covers"). Owner: SWE.
import { describe, expect, it } from "vitest";
import type { HorizonClient, WorldInput } from "../../client/HorizonClient";
import { HorizonError } from "../../contract/errors";
import type { World } from "../../contract/types";
import { coverFileError, MAX_COVER_BYTES, saveWorld } from "./worldSave";

const NOW = "2026-10-03T03:00:00.000Z";
const world = (id: string, input: Partial<WorldInput> & { name: string }): World => ({
  id, name: input.name, cover: input.cover ?? { kind: "preset", presetId: "cover_night_skyline" }, characterCount: 0,
  isSeed: false, createdAt: NOW, updatedAt: NOW, lastActiveAt: NOW,
});

function fakeClient(opts: { uploadFails?: boolean } = {}) {
  const calls: { method: string; args: unknown[] }[] = [];
  const worlds = {
    create: async (input: WorldInput) => { calls.push({ method: "create", args: [input] }); return world("wld_new", input); },
    update: async (id: string, patch: Partial<WorldInput>) => { calls.push({ method: "update", args: [id, patch] }); return world(id, { name: patch.name ?? "x", ...patch }); },
    uploadCover: async (id: string, file: File) => {
      calls.push({ method: "uploadCover", args: [id, file] });
      if (opts.uploadFails) throw new HorizonError("validation", "That file isn't a valid image.");
      return { ...world(id, { name: "My Street" }), cover: { kind: "upload" as const, url: `/assets/gen/${id}/cover_v1.webp` } };
    },
  } as unknown as HorizonClient["worlds"];
  return { client: { worlds }, calls };
}

const png = new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], "cover.png", { type: "image/png" });
const preset = { kind: "preset" as const, presetId: "cover_night_skyline" };

describe("world editor: covers are uploaded after the save", () => {
  it("new world with an uploaded cover: created with the preset cover, then one uploadCover call", async () => {
    const { client, calls } = fakeClient();
    const r = await saveWorld(client, { name: "My Street", cover: preset, file: png });
    expect(calls.map((c) => c.method)).toEqual(["create", "uploadCover"]);
    expect((calls[0].args[0] as WorldInput).cover).toEqual(preset);      // no data URL in the world record
    expect(calls[1].args).toEqual(["wld_new", png]);
    expect(r).toMatchObject({ created: true, world: { cover: { kind: "upload" } } });
    expect(r.uploadError).toBeUndefined();
  });

  it("an upload error keeps the saved world and reports why", async () => {
    const { client } = fakeClient({ uploadFails: true });
    const r = await saveWorld(client, { name: "My Street", cover: preset, file: png });
    expect(r.created).toBe(true);
    expect(r.world.id).toBe("wld_new");
    expect(r.uploadError).toBe("That file isn't a valid image.");
  });

  it("saving an existing world without a new file never uploads", async () => {
    const { client, calls } = fakeClient();
    const existing = world("wld_a", { name: "A" });
    const r = await saveWorld(client, { existing, name: "A2", cover: preset });
    expect(calls.map((c) => c.method)).toEqual(["update"]);
    expect(r.created).toBe(false);
  });

  it("oversized file: refused before anything is sent", () => {
    expect(coverFileError({ type: "image/jpeg", size: 6 * 1024 * 1024 })).toMatch(/over 5 MB/);
    expect(coverFileError({ type: "image/png", size: MAX_COVER_BYTES })).toBeNull();
    expect(coverFileError({ type: "image/gif", size: 10 })).toMatch(/PNG, JPEG or WebP/);
    expect(coverFileError({ type: "image/webp", size: 10 })).toBeNull();
  });
});
