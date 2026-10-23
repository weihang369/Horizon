// HorizonClient contract on the MockClient: the portable suite through a ManualClock harness, plus mock-only checks.
// The HttpClient runs the same portable suite through its own harness (backend /_test/* routes).
import { readFileSync } from "node:fs";
import path from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import type { Message, SessionEvent } from "../contract/types";
import type { LiveSession } from "../mock/engines/host";
import type { Dataset } from "../mock/db/dataset";
import { loadSeedDataset } from "../mock/db/loadSeed";
import { MockClient } from "../mock/MockClient";
import { ManualClock } from "../mock/time/Clock";
import type { ContractHarness } from "./clientContract.portable";
import { decisionCostUsd, FACE_CHECK_DECISION_TOKENS, TURN_PLAN_DECISION_TOKENS } from "../domain/cost";
import { PRICING } from "../mock/pricing.config";
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
    expect(src.match(/^\s+test\("M(1b|[2-7])", /gm)?.length).toBeGreaterThanOrEqual(50);
  });

  it("the mock runs every portable test: nothing is pending", () => {
    const src = readFileSync(path.resolve(__dirname, "clientContract.mock.test.ts"), "utf8");
    expect(src).toMatch(/runPortableContract\("MockClient", \(\) => mockHarness\(\)\);/);
  });

  it("the HTTP run declares M6, the last milestone: nothing is pending there either", () => {
    const src = readFileSync(path.resolve(__dirname, "clientContract.http.test.ts"), "utf8");
    expect(src).toMatch(/runPortableContract\("HttpClient", httpHarness, \{ supports: "M11" \}\);/);
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

  // M9 (turn-plan-emotion D20, D21; demo-data "Mock reactions dropped by a user message"): the mock's reactions are
  // re-checked, cancellable callbacks, and each completed AUTO reply with listeners charges one `reaction` decision.
  it("a user message drops pending mock reactions; the reply charged one simulated reaction decision", async () => {
    const h = await mockHarness();
    await h.setKey();
    const c = h.client;
    const s = await c.sessions.create({ worldId: "wld_seedSunnyHollow", mode: "group",
      characterIds: ["chr_seedHana", "chr_seedTakeshi", "chr_seedRin"] });
    const sid = s.session.id;
    await h.advance(3000);
    const events: SessionEvent[] = [];
    c.sessions.subscribe(sid, { sinceSeq: 0 }, (e) => events.push(e));
    const live = (h.mock as unknown as { lives: Map<string, LiveSession> }).lives.get(sid)!;
    const pending = () => {
      const d = live.player.cancel((e) => !!e.tag?.startsWith("react:"));
      live.player.insert(d);
      return d;
    };
    let dropped: string | undefined;
    for (let i = 0; i < 8 && !dropped; i++) {
      const decisionsBefore = (await c.usage.summary()).byCategory.decision;
      const seen = events.length;
      await c.chat.send(sid, `Dinner plans, take ${i}?`, { mentions: ["chr_seedHana"] });
      let end: SessionEvent | undefined;
      for (let t = 0; t < 20000 && !end; t += 50) {
        await h.advance(50);
        end = events.slice(seen).find((e) => e.type === "turn.end");
      }
      expect(end).toBeDefined();
      await h.advance(50);   // the charge lands at turn.end
      expect((await c.usage.summary()).byCategory.decision).toBeGreaterThan(decisionsBefore);
      const mid = (end!.payload as { messageId: string }).messageId;
      if (pending().some((e) => e.tag!.startsWith(`react:${mid}:`))) {
        await c.chat.send(sid, "Wait, hold on.", { mentions: ["chr_seedHana"] });
        await h.advance(6000);
        expect(events.filter((e) => e.type === "reaction" && (e.payload as { messageId: string }).messageId === mid)).toEqual([]);
        dropped = mid;
      } else {
        await h.advance(8000);
      }
    }
    expect(dropped).toBeDefined();
  });

  // M9 (turn-plan-emotion D24, D25; demo-data "Mock 1:1 turn"): a 1:1 reply is planned (one `turn_plan` charge and the
  // emotion row) and, when its face isn't neutral in AUTO, checked after faceCheckMs (a `face_check` charge and row).
  it("a mock 1:1 turn charges the plan and the face check and shows both rows, the reply cost unchanged", async () => {
    const h = await mockHarness();
    await h.setKey();
    const c = h.client;
    const s = await c.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedAmara"] });
    const sid = s.session.id;
    await h.advance(6000);
    let reply: Message | undefined;
    for (let i = 0; i < 10 && !reply; i++) {
      const before = (await c.usage.summary()).byCategory.decision;
      await c.chat.send(sid, `Tell me about your week, part ${i}.`);
      await h.advance(15000);
      const last = chars((await c.sessions.get(sid)).messages).at(-1)!;
      const added = (await c.usage.summary()).byCategory.decision - before;
      const plan = decisionCostUsd(TURN_PLAN_DECISION_TOKENS, PRICING.decision);
      const check = decisionCostUsd(FACE_CHECK_DECISION_TOKENS, PRICING.decision);
      if (last.emotion === "neutral") {
        expect(added).toBeCloseTo(plan, 9);
        continue;
      }
      expect(added).toBeCloseTo(plan + check, 9);
      reply = last;
    }
    expect(reply).toBeDefined();
    const rows = reply!.trace!.system1!.questions;
    expect(rows.map((r) => [r.id, r.answer])).toEqual([["emotion_reply", reply!.emotion], ["face_check", "yes"]]);
    expect(rows[1].result).toBe("shown_only");
    const calls = reply!.trace!.calls!.map((x) => x.purpose);
    expect(calls).toEqual(["turn_plan", "reply", "face_check"]);
    const replyCall = reply!.trace!.calls!.find((x) => x.purpose === "reply")!;
    expect(replyCall.costUsd).toBe(reply!.usage?.costUsd);                       // the reply's own cost is unchanged
  });

  it("Mock recap: the canned recap's charge has purpose episode_summary in category summary (group-watch D19, D21)", async () => {
    const h = await mockHarness();
    await h.setKey();
    const s = await h.mock.sessions.create({ worldId: "wld_seedSunnyHollow", mode: "watch", characterIds: ["chr_seedHana", "chr_seedTakeshi"],
      config: { premise: "A quiet evening at the bakery.", maxTurns: 10, paceMs: 500, openingSpeaker: "auto" } });
    await h.advance(8000);
    await h.mock.watch.pause(s.session.id);
    await h.advance(15000);
    await h.mock.watch.summarise(s.session.id);
    await h.advance(5000);
    expect(h.mock.chargedPurposes.filter((x) => x.sessionId === s.session.id))
      .toEqual([{ sessionId: s.session.id, category: "summary", purpose: "episode_summary" }]);
    expect((await h.mock.sessions.messages(s.session.id)).filter((m) => m.kind === "summary")).toHaveLength(1);
  });
  it("Mock verdict: the Arbiter verdict's charge has purpose verdict in category chat (debate D15, demo-data)", async () => {
    const h = await mockHarness();
    await h.setKey();
    const s = await h.mock.sessions.create({ worldId: "wld_seedMeridian", mode: "debate", characterIds: ["chr_seedAmara", "chr_seedVictor"],
      config: { motion: "This house would ban homework", format: "two_sided", sides: { prop: ["chr_seedAmara"], opp: ["chr_seedVictor"] },
        roundsPreset: "quick", phases: ["opening", "closing"], turnLength: "short", moderator: "user", verdictBy: "arbiter", rubric: [],
        autoAdvance: true, pauseMs: 1500 } });
    await h.advance(120000);
    const got = h.mock.chargedPurposes.filter((x) => x.sessionId === s.session.id && x.purpose === "verdict");
    expect(got).toEqual([{ sessionId: s.session.id, category: "chat", purpose: "verdict" }]);
  });
});

