// WLD-02 AC1: name required, 1–40 chars, unique (case-insensitive) among worlds. Owner: Builder A.
import type { World } from "../../contract/types";

export function validateWorldName(name: string, worlds: Pick<World, "id" | "name">[], selfId?: string): string | null {
  const n = name.trim();
  if (!n) return "Give your world a name.";
  if (n.length > 40) return "Keep it to 40 characters.";
  if (worlds.some((w) => w.id !== selfId && w.name.trim().toLowerCase() === n.toLowerCase())) return "You already have a world with that name.";
  return null;
}
