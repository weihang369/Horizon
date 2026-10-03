// Line picking for the live fake AI (EE paper §2.3): score bank lines by keyword overlap with the prompt,
// otherwise rotate with a PRNG seeded by sessionId + turn, so every review is repeatable. Owner: EE.
import type { Character } from "../../contract/types";
import type { Rng } from "../rng";
import { directionLines, genericChat, sceneLines } from "./generic";
import { SEED_BANKS } from "./seedBanks";
import type { BankLine } from "./types";

export type { BankLine } from "./types";
export { answerTo, debateLine, directionLines } from "./generic";

function score(line: BankLine, words: string): number {
  if (!line.tags?.length) return 0;
  let s = 0;
  for (const t of line.tags) if (words.includes(t)) s += t.length > 4 ? 2 : 1;
  return s;
}

/** Pick a chat line for `c` answering `prompt`, avoiding the last texts used in this session. */
export function pickChatLine(c: Character, prompt: string, rng: Rng, recent: string[] = []): BankLine {
  const bank = SEED_BANKS[c.id]?.chat ?? genericChat(c);
  const words = ` ${prompt.toLowerCase()} `;
  const fresh = bank.filter((l) => !recent.includes(l.text));
  const pool = fresh.length ? fresh : bank;
  const scored = pool.map((l) => ({ l, s: score(l, words) })).filter((x) => x.s > 0).sort((a, b) => b.s - a.s);
  if (scored.length) return scored[0].l;
  return rng.pick(pool.filter((l) => !l.tags?.length).length ? pool.filter((l) => !l.tags?.length) : pool);
}

export function pickSceneLine(c: Character, premise: string, rng: Rng, recent: string[] = [], directionNote?: string): BankLine {
  if (directionNote) return rng.pick(directionLines(directionNote));
  const bank = [...(SEED_BANKS[c.id]?.scene ?? []), ...sceneLines(c, premise)];
  const fresh = bank.filter((l) => !recent.includes(l.text));
  return rng.pick(fresh.length ? fresh : bank);
}

/** Opening line of a fresh 1:1 session. */
export const greetingFor = (c: Character): BankLine => ({ text: c.profile.greeting || genericChat(c)[0].text, emotion: "happy" });
