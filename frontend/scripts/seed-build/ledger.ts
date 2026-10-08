// ~2.5 weeks of usage records (SET-09 spend view), derived from the compiled sessions + character creation.
import type { Message, UsageRecord } from "../../src/contract/types";
import { MODELS, PRICING } from "../../src/mock/pricing.config";
import type { CharacterDef } from "./data/characters";

const add = (ms: number, deltaMs: number) => new Date(ms + deltaMs).toISOString().replace(".000Z", "Z");

export function ledgerFor(
  sessions: { sessionId: string; mode: string; messages: Message[]; mock: boolean }[],
  characters: CharacterDef[],
): { seed: UsageRecord[]; mock: UsageRecord[] } {
  const seed: UsageRecord[] = [];
  const mock: UsageRecord[] = [];
  let n = 0;
  const push = (target: UsageRecord[], r: Omit<UsageRecord, "id">) => target.push({ id: `usg_${(++n).toString().padStart(4, "0")}`, ...r });

  for (const c of characters) {
    const target = c.mock ? mock : seed;
    const created = Date.parse(c.character.createdAt);
    const cid = c.character.id;
    const g = PRICING.generation;
    push(target, { at: add(created, 5_000), category: "profile", model: PRICING.chat.model, characterId: cid, costUsd: g.profileDraft, estimatedCostUsd: g.profileDraft, latencyMs: 4100 });
    if (c.character.appearance.basePortraitUrl) {
      const cands = c.character.appearance.candidates.length || 1;
      for (let i = 0; i < cands; i++) push(target, { at: add(created, 60_000 + i * 1000), category: "image", model: "qwen/qwen-image-3", characterId: cid, costUsd: g.portrait, estimatedCostUsd: g.portrait, latencyMs: 19_800 });
      const emos = Object.entries(c.character.emotions).filter(([e, v]) => e !== "neutral" && v).length;
      for (let i = 0; i < emos; i++) push(target, { at: add(created, 180_000 + i * 16_000), category: "image", model: "qwen/qwen-image-3", characterId: cid, costUsd: g.emotionEdit, estimatedCostUsd: g.emotionEdit, latencyMs: 15_200 });
      if (c.renderBlink) push(target, { at: add(created, 300_000), category: "image", model: "qwen/qwen-image-3", characterId: cid, costUsd: g.blinkFrame, estimatedCostUsd: g.blinkFrame, latencyMs: 14_900 });
    }
    if (c.song) push(target, { at: add(created, 420_000), category: "music", model: MODELS.music, characterId: cid, costUsd: g.song, estimatedCostUsd: g.song, latencyMs: 41_000 });
  }

  for (const s of sessions) {
    const target = s.mock ? mock : seed;
    for (const m of s.messages) {
      if (!m.usage || !m.author.characterId) continue;
      if (s.mode === "group") {
        push(target, { at: m.createdAt, category: "decision", model: PRICING.decision.model, provider: PRICING.decision.provider, sessionId: s.sessionId, tokensIn: 620, tokensOut: 12, costUsd: 0.000013, latencyMs: 180 });
      }
      push(target, {
        at: m.createdAt, category: "chat", model: PRICING.chat.model, provider: PRICING.chat.provider, pricePeriod: m.trace?.model?.pricePeriod ?? "off_peak",
        sessionId: s.sessionId, characterId: m.author.characterId,
        tokensIn: m.usage.tokensIn, tokensCached: m.usage.tokensCached, tokensOut: m.usage.tokensOut,
        costUsd: m.usage.costUsd, energyPoints: m.usage.energySpent, latencyMs: m.usage.totalMs,
      });
    }
    if (s.mode === "debate" && s.messages.some((m) => m.kind === "verdict")) {
      const v = s.messages.find((m) => m.kind === "verdict")!;
      push(target, { at: v.createdAt, category: "summary", model: PRICING.chat.model, provider: PRICING.chat.provider, sessionId: s.sessionId, tokensIn: 6400, tokensCached: 5200, tokensOut: 420, costUsd: 0.00046, latencyMs: 6200 });
    }
  }

  // An energy top-up for Rin (ENG-05), so the spend view shows the category.
  push(seed, { at: "2026-09-27T08:00:00Z", category: "energy_topup", characterId: "chr_seedRin", costUsd: 0.05, energyPoints: 500 });

  const byTime = (a: UsageRecord, b: UsageRecord) => a.at.localeCompare(b.at) || a.id.localeCompare(b.id);
  return { seed: seed.sort(byTime), mock: mock.sort(byTime) };
}
