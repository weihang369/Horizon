// The World editor's save flow (worlds "The world editor uploads covers", generation-jobs design D11). Owner: SWE.
// A picked cover file is never inlined into the world record: the world is created or saved first (with its previous or
// preset cover), then the file goes through `worlds.uploadCover`. An upload error leaves the world saved and is shown in
// the editor, which then edits that world (so saving again never creates a second one).
import type { HorizonClient, WorldInput } from "../../client/HorizonClient";
import type { HorizonErrorShape } from "../../contract/errors";
import type { World } from "../../contract/types";

export const COVER_TYPES = ["image/png", "image/jpeg", "image/webp"] as const;
export const MAX_COVER_BYTES = 5 * 1024 * 1024;

/** The editor's own check before anything is sent (the client and the backend check again, by content). */
export function coverFileError(f: { type: string; size: number }): string | null {
  if (!(COVER_TYPES as readonly string[]).includes(f.type)) return "Pick a PNG, JPEG or WebP image.";
  if (f.size > MAX_COVER_BYTES) return "That image is over 5 MB. Try a smaller one.";
  return null;
}

export interface SaveInput {
  existing?: World;
  name: string;
  cover: WorldInput["cover"];
  you?: WorldInput["you"];
  file?: File | null;
}

export interface SaveResult {
  world: World;
  created: boolean;
  /** Set when the world was saved but its cover upload failed. */
  uploadError?: string;
}

export async function saveWorld(c: Pick<HorizonClient, "worlds">, input: SaveInput): Promise<SaveResult> {
  const body = { name: input.name, cover: input.cover, you: input.you };
  const world = input.existing ? await c.worlds.update(input.existing.id, body) : await c.worlds.create(body);
  const created = !input.existing;
  if (!input.file) return { world, created };
  try {
    return { world: await c.worlds.uploadCover(world.id, input.file), created };
  } catch (e) {
    return { world, created, uploadError: (e as HorizonErrorShape)?.message ?? "Couldn't upload the cover." };
  }
}
