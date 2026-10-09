// HorizonClient contract (EE paper §2.10, rev 1.3): the executable spec that BOTH clients must pass.
// Portable: it touches only the HorizonClient interface plus a ContractHarness (time, scenarios, reset, key).
// It must never import from src/mock: the MockClient harness lives in clientContract.mock.test.ts, and the M1b
// HttpClient harness drives the backend's /_test/* routes instead. Owner: EE.
import { afterEach, describe, expect, it } from "vitest";
import type { Message, Session, SessionEvent } from "../contract/types";
import { initialRuntime, orderedMessages, reduceAll } from "../engine/sessionReducer";
import { HorizonError } from "../contract/errors";
import { CharacterSchema, GlobalEventSchema, KnowledgeChunkSchema, MessageSchema, SessionEventSchema } from "../contract/schemas";
import type { GlobalEvent, HorizonClient, JobEvent } from "./HorizonClient";

/** Scenario ids every harness must support (the backend mirrors them under /_test/scenario). */
export type ContractScenario =
  | "character_exhausted" | "stream_cut" | "image_fail_partial" | "network_down" | "no_worlds" | "rush_hour";

export interface ContractHarness {
  client: HorizonClient;
  /** Advance the client's clock by `ms` and let scheduled work run. */
  advance(ms: number): Promise<void>;
  setScenario(id: ContractScenario): Promise<void>;
  /** "Reset demo data": re-seed seed records, keep user data (D-70, rev 1.3). */
  reset(): Promise<void>;
  /** Set a valid key (leaves demo mode). */
  setKey(): Promise<void>;
  /** Release the client's streams after the test (HTTP harness). */
  dispose?(): void | Promise<void>;
}
export type MakeHarness = () => Promise<ContractHarness>;

/** The backend milestone whose routes a test needs (doc backend/06). The mock supports everything ("all"). */
export type Milestone = "M1b" | "M2" | "M3" | "M4" | "M5" | "M6";

/** A valid 16×9 PNG (83 bytes) for the cover upload tests. */
const TINY_PNG = [
  137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82, 0, 0, 0, 16, 0, 0, 0, 9, 8, 2, 0, 0, 0, 180, 72, 59, 101, 0, 0,
  0, 26, 73, 68, 65, 84, 120, 156, 99, 212, 59, 178, 141, 129, 20, 192, 68, 146, 106, 134, 81, 13, 196, 1, 146, 131, 21, 0, 231,
  232, 1, 186, 121, 203, 221, 186, 0, 0, 0, 0, 73, 69, 78, 68, 174, 66, 96, 130,
];
export const MILESTONES: readonly Milestone[] = ["M1b", "M2", "M3", "M4", "M5", "M6"];
export interface PortableOptions {
  /** The latest milestone this client's backend implements. Later tests are listed as `[pending Mx]`, never silently skipped. */
  supports: Milestone | "all";
}

const code = async (p: Promise<unknown>) => {
  try {
    await p;
    return "ok";
  } catch (e) {
    expect(e).toBeInstanceOf(HorizonError);
    return (e as HorizonError).code;
  }
};
const fail = async (p: Promise<unknown>): Promise<HorizonError> => {
  try {
    await p;
  } catch (e) {
    expect(e).toBeInstanceOf(HorizonError);
    return e as HorizonError;
  }
  throw new Error("expected a rejection");
};
const chars = (msgs: Message[]) => msgs.filter((m) => m.author.type === "character");
/** Wait (real time) for something a remote client delivers asynchronously, e.g. over SSE. */
async function eventually(cond: () => boolean, ms = 5000): Promise<void> {
  const end = Date.now() + ms;
  while (!cond()) {
    if (Date.now() > end) throw new Error("timed out waiting for a condition");
    await new Promise((r) => setTimeout(r, 20));
  }
}
/** The session a seed recording starts from (as scripts/seed-build builds it); its events set the rest. */
function seedBase(final: Session): Session {
  const { lastMessageAt: _l, pausedReason: _p, ...rest } = final;
  return { ...rest, status: "active", state: null, costUsd: 0, messageCount: 0, updatedAt: final.createdAt };
}
const COVER = { kind: "preset" as const, presetId: "cover_night_skyline" };

export function runPortableContract(label: string, makeHarness: MakeHarness, opts: PortableOptions = { supports: "all" }): void {
  /** Declare a portable test with the milestone it needs; unknown milestones fail the suite at definition time. */
  function test(m: Milestone, name: string, fn: () => Promise<void>, timeout?: number): void {
    if (!MILESTONES.includes(m)) throw new Error(`portable test "${name}": unknown milestone ${String(m)}`);
    const runs = opts.supports === "all" || MILESTONES.indexOf(m) <= MILESTONES.indexOf(opts.supports);
    if (runs) it(name, fn, timeout);
    else it.skip(`[pending ${m}] ${name}`, fn);
  }

  const made: ContractHarness[] = [];
  afterEach(async () => {
    for (const h of made.splice(0)) await h.dispose?.();
  });

  async function make(opts: { key?: boolean } = {}) {
    const h = await makeHarness();
    made.push(h);
    const c = h.client;
    if (opts.key) await h.setKey();
    const events: SessionEvent[] = [];
    const globals: GlobalEvent[] = [];
    c.onGlobal((e) => globals.push(e));
    const watch = (sid: string) => c.sessions.subscribe(sid, { sinceSeq: 0 }, (e) => events.push(e));
    return { c, h, tick: h.advance, events, globals, watch, setScenario: h.setScenario, reset: h.reset };
  }

  describe(`HorizonClient contract (${label})`, () => {
    test("M1b", "queries work without a key (R15 demo mode)", async () => {
      const { c } = await make();
      expect((await c.settings.get()).openRouterKeyStatus).toBe("missing");
      const worlds = await c.worlds.list();
      expect(worlds.map((w) => w.id).sort()).toEqual(["wld_seedMeridian", "wld_seedSunnyHollow"]);
      expect(worlds.find((w) => w.id === "wld_seedMeridian")?.characterCount).toBeGreaterThanOrEqual(3);
      const roster = await c.characters.list("wld_seedSunnyHollow");
      expect(roster.some((x) => x.status === "archived")).toBe(false);
      expect((await c.characters.list("wld_seedSunnyHollow", { includeArchived: true })).some((x) => x.status === "archived")).toBe(true);
      expect((await c.sessions.list("wld_seedMeridian")).length).toBeGreaterThanOrEqual(5);
    });

    test("M4", "live actions without a key reject with missing_key (R15 demo mode)", async () => {
      const { c } = await make();
      expect(await code(c.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedAmara"] }))).toBe("missing_key");
      expect(await code(c.jobs.start({ characterId: "chr_mockSarah", kind: "portrait_candidates" }))).toBe("missing_key");
    });

    // client-contract "Key validity is learned from the provider": only what both clients share. The mock knows a
    // bad key at once (mock-only test); the backend learns it from OpenRouter's 401 (its test-mode fake provider).
    test("M2", "key validity: a rejected key reads invalid after testConnection; a good key is set and passes", async () => {
      const { c } = await make();
      await c.settings.setKey("sk-or-bad-zzz");
      expect(await code(c.settings.testConnection())).toBe("invalid_key");
      const bad = await c.settings.get();
      expect([bad.openRouterKeyStatus, bad.demoMode]).toEqual(["invalid", true]);
      const s = await c.settings.setKey("sk-or-good");
      expect(s.openRouterKeyStatus).toBe("set");
      expect(s.demoMode).toBe(false);
      expect((await c.settings.testConnection()).ok).toBe(true);
    });

    test("M3", "1:1: greeting, then send → user message, streamed reply, energy drain, ledger row", async () => {
      const { c, tick, events, watch } = await make({ key: true });
      const before = (await c.characters.get("chr_seedAmara")).energy.current;
      const snap = await c.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedAmara"] });
      expect(snap.session.isSeed).toBe(false);
      watch(snap.session.id);
      await tick(6000);
      let msgs = await c.sessions.messages(snap.session.id);
      expect(chars(msgs)).toHaveLength(1);
      expect(chars(msgs)[0].status).toBe("complete");
      await c.chat.send(snap.session.id, "I've had a headache for three days");
      await tick(12000);
      msgs = await c.sessions.messages(snap.session.id);
      expect(msgs.filter((m) => m.author.type === "user")).toHaveLength(1);
      const reply = chars(msgs)[1];
      expect(reply.status).toBe("complete");
      expect(reply.trace?.energy?.spent).toBeGreaterThan(0);
      const wanted = ["turn.next", "turn.thinking", "turn.start", "token", "emotion", "turn.end", "energy", "insight", "message"];
      // A remote client receives the stream asynchronously: wait for delivery (client-contract spec).
      await eventually(() => wanted.every((t) => events.some((e) => e.type === t)) && events.some((e) => e.type === "insight" && (e.payload as { messageId: string }).messageId === reply.id));
      const types = new Set(events.map((e) => e.type));
      for (const t of wanted) expect(types.has(t as SessionEvent["type"]), t).toBe(true);
      for (let i = 1; i < events.length; i++) expect(events[i].seq).toBe(events[i - 1].seq + 1);
      const after = (await c.characters.get("chr_seedAmara")).energy.current;
      expect(after).toBeLessThan(before);
      expect((await c.usage.summary()).byCategory.chat).toBeGreaterThan(0);
    });

    test("M3", "subscribe(sinceSeq) replays the backlog without gaps or duplicates", async () => {
      const { c, tick } = await make({ key: true });
      const snap = await c.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedMei"] });
      await tick(6000);
      const all = await c.sessions.events(snap.session.id);
      const got: number[] = [];
      c.sessions.subscribe(snap.session.id, { sinceSeq: 3 }, (e) => got.push(e.seq));
      await tick(10);
      const want = all.filter((e) => e.seq > 3).map((e) => e.seq);
      await eventually(() => got.length >= want.length);
      expect(got.slice(0, want.length)).toEqual(want);
    });

    test("M3", "seed sessions are replay-only; forkSeedSession(atSeq) continues live from the playhead (R16)", async () => {
      const { c, tick } = await make({ key: true });
      expect(await code(c.chat.send("ses_seedAmaraHeadache", "hi"))).toBe("conflict");
      const events = await c.sessions.events("ses_seedDebate4Day");
      const at = events[Math.floor(events.length / 3)].seq;
      const fork = await c.sessions.forkSeedSession("ses_seedDebate4Day", at);
      expect(fork.session.isSeed).toBe(false);
      expect(fork.session.continuedFrom).toBe("ses_seedDebate4Day");
      expect(fork.session.status).toBe("paused");
      expect(fork.messages.every((m) => m.status !== "streaming")).toBe(true);
      const full = await c.sessions.messages("ses_seedDebate4Day");
      expect(fork.messages.length).toBeLessThan(full.length);
      const n = fork.messages.length;
      await c.debate.resume(fork.session.id);
      await tick(30000);
      expect((await c.sessions.messages(fork.session.id)).length).toBeGreaterThan(n);
      // The seed recording is untouched.
      expect((await c.sessions.events("ses_seedDebate4Day")).length).toBe(events.length);
    });

    test("M3", "debate (quick, arbiter) runs to a verdict and ends", async () => {
      const { c, tick } = await make({ key: true });
      const s = await c.sessions.create({
        worldId: "wld_seedMeridian", mode: "debate", characterIds: ["chr_seedAmara", "chr_seedVictor"],
        config: { motion: "This house would tax sugary drinks", format: "two_sided", sides: { prop: ["chr_seedAmara"], opp: ["chr_seedVictor"] }, roundsPreset: "quick", phases: ["opening", "closing"], turnLength: "short", moderator: "user", verdictBy: "arbiter", rubric: [], autoAdvance: true, pauseMs: 1500 },
      });
      await tick(90000);
      const { session, messages } = await c.sessions.get(s.session.id);
      expect(session.status).toBe("ended");
      expect(chars(messages)).toHaveLength(4);
      expect(messages.some((m) => m.kind === "verdict")).toBe(true);
      const st = session.state as { phase: string; verdict?: { decidedBy: string; scores?: unknown[] } };
      expect(st.phase).toBe("ended");
      expect(st.verdict?.decidedBy).toBe("arbiter");
    });

    test("M3", "watch stops at the turn cap with turn_cap; Continue +10 extends it", async () => {
      const { c, tick } = await make({ key: true });
      const s = await c.sessions.create({
        worldId: "wld_seedSunnyHollow", mode: "watch", characterIds: ["chr_seedHana", "chr_seedTakeshi"],
        config: { premise: "Rainy afternoon at the shop.", maxTurns: 10, paceMs: 500, openingSpeaker: "auto" },
      });
      await tick(200000);
      let snap = await c.sessions.get(s.session.id);
      expect(chars(snap.messages)).toHaveLength(10);
      expect(snap.session.pausedReason).toBe("turn_cap");
      await c.watch.extendWatch(s.session.id, 10);
      await tick(10000);
      snap = await c.sessions.get(s.session.id);
      expect(chars(snap.messages).length).toBeGreaterThan(10);
    });

    test("M3", "group: @mentioning an exhausted character gives an asleep note + energy_exhausted (ENG-04)", async () => {
      const { c, tick, events, watch, setScenario } = await make({ key: true });
      await setScenario("character_exhausted");
      const s = await c.sessions.create({ worldId: "wld_seedSunnyHollow", mode: "group", characterIds: ["chr_seedHana", "chr_seedTakeshi"] });
      watch(s.session.id);
      await c.chat.send(s.session.id, "Dad, dinner?", { mentions: ["chr_seedTakeshi"] });
      await tick(15000);
      const msgs = await c.sessions.messages(s.session.id);
      expect(msgs.some((m) => m.kind === "system_note" && /Takeshi is asleep/.test(m.content))).toBe(true);
      await eventually(() => events.some((e) => e.type === "error" && (e.payload as { code: string }).code === "energy_exhausted"));
      expect(chars(msgs).every((m) => m.author.characterId !== "chr_seedTakeshi")).toBe(true);
      await c.characters.topUpEnergy("chr_seedTakeshi", 500);
      expect((await c.characters.get("chr_seedTakeshi")).energy.current).toBe(500);
    });

    test("M3", "stream cut: error(network) then turn.end(interrupted)", async () => {
      const { c, tick, setScenario } = await make({ key: true });
      const s = await c.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedVictor"] });
      await tick(6000);
      await setScenario("stream_cut");
      await c.chat.send(s.session.id, "Define your terms, counsel. What exactly do you mean by a fair trial in this case?");
      await tick(12000);
      const last = chars(await c.sessions.messages(s.session.id)).at(-1)!;
      expect(last.status).toBe("interrupted");
      expect(last.error?.code).toBe("network");
    });

    test("M3", "Stop interrupts a streaming reply (interruptedBy user)", async () => {
      const { c, tick } = await make({ key: true });
      const s = await c.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedVictor"] });
      await tick(6000);
      await c.chat.send(s.session.id, "Tell me everything about precedent.");
      // Stop only once the reply is mid-stream, so the test doesn't race the virtual clock under load.
      for (let i = 0; i < 40; i++) {
        await tick(250);
        if ((await c.sessions.messages(s.session.id)).some((m) => m.status === "streaming")) break;
      }
      await c.chat.stop(s.session.id);
      await tick(1000);
      const last = chars(await c.sessions.messages(s.session.id)).at(-1)!;
      expect(last.status).toBe("interrupted");
      expect(last.interruptedBy).toBe("user");
    });

    test("M3", "daily cap: spend reaching the cap pauses the session and blocks further sends (STATE-06)", async () => {
      const { c, tick, globals } = await make({ key: true });
      await c.settings.update({ budget: { dailyCapUsd: 0.00005 } });
      const s = await c.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedAmara"] });
      await tick(8000);
      await eventually(() => globals.some((g) => g.type === "budget.reached"));
      expect((await c.sessions.get(s.session.id)).session.pausedReason).toBe("daily_budget");
      expect(await code(c.chat.send(s.session.id, "hello?"))).toBe("daily_budget_exceeded");
    });

    test("M4", "creation pipeline: draft → profile job → portrait candidate → lock → emotions (Lean)", async () => {
      const { c, tick } = await make({ key: true });
      const { character, job } = await c.characters.createDraft("wld_seedMeridian", { seedPrompt: "Sarah, a doctor", intent: "expert" });
      expect(character.status).toBe("draft");
      const seen: JobEvent[] = [];
      c.jobs.subscribe(job.id, (e) => seen.push(e));
      await tick(5000);
      expect(seen.at(-1)?.type).toBe("job.done");
      let ch = await c.characters.get(character.id);
      expect(ch.profile.name).toBe("Sarah");
      expect(ch.profile.role.length).toBeGreaterThan(0);
      const pj = await c.jobs.start({ characterId: character.id, kind: "portrait_candidates" });
      expect(pj.tasks).toHaveLength(1);
      await tick(21000);
      expect((await c.jobs.get(pj.id)).status).toBe("succeeded");
      ch = await c.characters.get(character.id);
      const cand = ch.appearance.candidates.find((x) => x.status === "ready")!;
      expect(cand.url.length).toBeGreaterThan(0);
      ch = await c.characters.lockPortrait(character.id, cand.id);
      expect(ch.emotions.neutral?.url).toBe(cand.url);
      const ej = await c.jobs.start({ characterId: character.id, kind: "emotion_set" });
      expect(ej.tasks.map((t) => t.emotion)).toEqual(["happy", "sad", "angry"]);
      await tick(40000);
      ch = await c.characters.get(character.id);
      expect(ch.emotions.happy && ch.emotions.sad && ch.emotions.angry).toBeTruthy();
      expect(ch.emotions.surprised).toBeNull();
      expect((await c.characters.approve(character.id)).status).toBe("approved");
    });

    test("M4", "partial image failure: task 2 fails at 60 %, Retry succeeds (F6)", async () => {
      const { c, tick, setScenario } = await make({ key: true });
      await c.settings.update({ generationMode: "standard" });
      await setScenario("image_fail_partial");
      const job = await c.jobs.start({ characterId: "chr_mockSarah", kind: "portrait_candidates" });
      await tick(25000);
      const done = await c.jobs.get(job.id);
      expect(done.status).toBe("partial");
      const failed = done.tasks.find((t) => t.status === "failed")!;
      await c.jobs.retryTask(job.id, failed.id);
      await tick(25000);
      expect((await c.jobs.get(job.id)).status).toBe("succeeded");
    });

    test("M3", "an overlay scenario keeps user-created sessions, so it lands on the current screen (DoD #2)", async () => {
      const { c, setScenario } = await make({ key: true });
      const fork = await c.sessions.forkSeedSession("ses_seedDebate4Day");
      await setScenario("character_exhausted");
      expect((await c.sessions.messages(fork.session.id)).length).toBe(fork.messages.length);
    });

    test("M6", "network down rejects queries too; Reset demo data restores the shipped fixtures", async () => {
      const { c, globals, setScenario, reset } = await make({ key: true });
      await setScenario("network_down");
      expect(await code(c.worlds.list())).toBe("network");
      await setScenario("no_worlds");
      expect(await c.worlds.list()).toEqual([]);
      await reset();
      expect((await c.worlds.list()).length).toBe(2);
      expect(globals.filter((g) => g.type === "mock.reset").length).toBeGreaterThanOrEqual(2);
    });

    test("M1b", "knowledge (D-59): knowledgeSource returns ordered passages; a seed source is readable", async () => {
      const { c } = await make();
      const { source, chunks } = await c.characters.knowledgeSource("kno_seedAmara1");
      // The mock simulates seed vectors (indexed); the backend has none until "Index seed knowledge" (OQ-1).
      expect(["indexed", "keyword_only"]).toContain(source.status);
      expect(chunks.length).toBe(source.chunks);
      expect(chunks.map((k) => k.index)).toEqual(chunks.map((_, i) => i));
      for (const k of chunks) KnowledgeChunkSchema.parse(k);
      expect(await code(c.characters.knowledgeSource("kno_nope"))).toBe("not_found");
    });

    // Live citations need retrieval over indexed seed knowledge, which arrives with M5 (session-runtime OQ-2).
    test("M5", "knowledge (D-59): live replies cite indexed passages (zod-valid)", async () => {
      const { c, tick, events, watch } = await make({ key: true });

      const snap = await c.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedAmara"] });
      watch(snap.session.id);
      await tick(6000);
      let cited: Message | undefined;
      for (let i = 0; i < 8 && !cited; i++) {
        await c.chat.send(snap.session.id, `What does the review say about burnout? (${i})`);
        await tick(14000);
        cited = chars(await c.sessions.messages(snap.session.id)).find((m) => m.citations?.length);
      }
      expect(cited, "a live Amara reply cites her knowledge").toBeTruthy();
      MessageSchema.parse(cited);
      for (const ct of cited!.citations!) {
        expect(cited!.content).toContain(`[${ct.n}]`);
        expect(ct.quote.length).toBeLessThanOrEqual(400);
      }
      const end = events.find((e) => e.type === "turn.end" && (e.payload as { messageId: string }).messageId === cited!.id);
      expect(end && SessionEventSchema.parse(end)).toBeTruthy();
      expect((end!.payload as { citations?: unknown[] }).citations?.length).toBe(cited!.citations!.length);
      const k = cited!.trace?.knowledge;
      expect(k?.retrieved.some((r) => r.cited)).toBe(true);
      expect(k?.retrieved.some((r) => !r.cited)).toBe(true);
      expect(cited!.trace?.context?.used.knowledge).toBeGreaterThan(0);
    });

    test("M3", "Markdown export turns citation markers into [^n] footnotes with title, locator and quote (D-59)", async () => {
      const { c } = await make();
      const md = await c.sessions.export("ses_seedDebate4Day");
      expect(md).toContain("[^1]");
      expect(md).not.toMatch(/[a-z.,]\[\d\]/);
      expect(md).toContain("## Sources");
      expect(md).toMatch(/\[\^1\]: Meridian Shift Fatigue Review 2025\.pdf, p\. 4\. "/);
    });

    // ── rev 1.3: error codes (client-contract spec) ─────────────────────────
    test("M1b", "unknown records reject with not_found (not network)", async () => {
      const { c } = await make();
      expect(await code(c.sessions.get("ses_nope"))).toBe("not_found");
      expect(await code(c.characters.get("chr_nope"))).toBe("not_found");
      expect(await code(c.worlds.get("wld_nope"))).toBe("not_found");
      expect(await code(c.jobs.get("job_nope"))).toBe("not_found");
      const e = await fail(c.sessions.messages("ses_nope"));
      expect(e.retryable).toBe(false);
    });

    test("M3", "sending into a seed recording or an ended session rejects with conflict", async () => {
      const { c } = await make({ key: true });
      expect(await code(c.chat.send("ses_seedAmaraHeadache", "hi"))).toBe("conflict");
      const s = await c.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedAmara"] });
      await c.sessions.end(s.session.id);
      expect(await code(c.chat.send(s.session.id, "still there?"))).toBe("conflict");
    });

    test("M3", "a wrong cast size rejects with validation and names the limit in details", async () => {
      const { c } = await make({ key: true });
      const e = await fail(c.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedAmara", "chr_seedVictor"] }));
      expect(e.code).toBe("validation");
      expect(e.details).toMatchObject({ min: 1, max: 1 });
    });

    test("M3", "a second streaming session is refused with conflict naming the live one", async () => {
      const { c, tick } = await make({ key: true });
      const a = await c.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedAmara"] });
      await tick(6000);
      await c.chat.send(a.session.id, "Tell me everything about the rota review, in detail.");
      for (let i = 0; i < 40; i++) {
        await tick(250);
        if ((await c.sessions.messages(a.session.id)).some((m) => m.status === "streaming")) break;
      }
      const e = await fail(c.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedVictor"] }));
      expect(e.code).toBe("conflict");
      expect(e.details?.activeSessionId).toBe(a.session.id);
      await c.sessions.leave(a.session.id);
      expect(await code(c.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedVictor"] }))).toBe("ok");
    });

    // ── rev 1.3: settings, usage, trace, global stream (client-contract spec) ─
    test("M2", "estReplyPoints is read-only config and models include the embedding model", async () => {
      const { c } = await make({ key: true });
      const s = await c.settings.get();
      expect(s.energy.estReplyPoints).toEqual({ off_peak: 4, peak: 8 });
      expect(s.models.embedding.length).toBeGreaterThan(0);
      const after = await c.settings.update({ energy: { estReplyPoints: { off_peak: 1, peak: 1 } } });
      expect(after.energy.estReplyPoints).toEqual({ off_peak: 4, peak: 8 });
      expect((await c.settings.testModel("embedding")).model).toBe(s.models.embedding);
    });

    test("M1b", "the usage summary has an embedding bucket", async () => {
      const { c } = await make();
      expect((await c.usage.summary()).byCategory.embedding).toBe(0);
    });

    test("M3", "a live reply's trace lists its paid calls, with the reply cost matching usage", async () => {
      const { c, tick } = await make({ key: true });
      const snap = await c.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedAmara"] });
      await tick(6000);
      await c.chat.send(snap.session.id, "Quick question about sleep.");
      await tick(14000);
      const reply = chars(await c.sessions.messages(snap.session.id)).at(-1)!;
      const call = reply.trace?.calls?.find((x) => x.purpose === "reply");
      expect(call, "reply call in trace.calls").toBeTruthy();
      expect(call!.costUsd).toBe(reply.usage?.costUsd);
    });

    test("M3", "group turns add a route call to the trace", async () => {
      const { c, tick } = await make({ key: true });
      const s = await c.sessions.create({ worldId: "wld_seedSunnyHollow", mode: "group", characterIds: ["chr_seedHana", "chr_seedTakeshi"] });
      await c.chat.send(s.session.id, "What should we cook tonight?");
      await tick(20000);
      const replies = chars(await c.sessions.messages(s.session.id));
      expect(replies.some((m) => m.trace?.calls?.some((x) => x.purpose === "route"))).toBe(true);
    });

    test("M4", "job task updates are mirrored onto the global stream", async () => {
      const { c, tick, globals } = await make({ key: true });
      const job = await c.jobs.start({ characterId: "chr_mockSarah", kind: "portrait_candidates" });
      await tick(25000);
      const tasks = globals.filter((g) => g.type === "task.update" && g.jobId === job.id);
      expect(tasks.length).toBeGreaterThan(0);
      for (const g of tasks) GlobalEventSchema.parse(g);
    });

    // ── rev 1.3: energy (energy spec, D-76, D-78) ─────────────────────────────
    test("M3", "one threshold: 6 ⚡ is tired off-peak but exhausted (and skipped) at peak", async () => {
      const { c, tick, events, watch, setScenario } = await make({ key: true });
      await setScenario("character_exhausted"); // Takeshi at 0 ⚡
      await c.characters.topUpEnergy("chr_seedTakeshi", 6);
      expect((await c.characters.get("chr_seedTakeshi")).energy.state).toBe("tired");
      await setScenario("rush_hour");
      expect((await c.settings.get()).pricing.period).toBe("peak");
      expect((await c.characters.get("chr_seedTakeshi")).energy.state).toBe("exhausted");
      const s = await c.sessions.create({ worldId: "wld_seedSunnyHollow", mode: "group", characterIds: ["chr_seedHana", "chr_seedTakeshi"] });
      watch(s.session.id);
      await c.chat.send(s.session.id, "Anyone hungry?");
      await tick(20000);
      const isTakeshiEnergy = (e: SessionEvent) => e.type === "energy" && (e.payload as { characterId: string }).characterId === "chr_seedTakeshi";
      await eventually(() => events.some(isTakeshiEnergy));
      const opening = events.find(isTakeshiEnergy);
      expect((opening?.payload as { state: string }).state).toBe("exhausted");
      const msgs = await c.sessions.messages(s.session.id);
      expect(chars(msgs).every((m) => m.author.characterId !== "chr_seedTakeshi")).toBe(true);
      const skipped = msgs.flatMap((m) => m.trace?.routing?.skipped ?? []);
      expect(skipped).toContainEqual({ characterId: "chr_seedTakeshi", reason: "exhausted" });
    });

    test("M2", "top-up gate (D-76): repeated top-ups are bounded by today's budget headroom", async () => {
      const { c } = await make({ key: true });
      await c.settings.update({ budget: { dailyCapUsd: 0.6 } });
      const spent = (await c.settings.get()).spentTodayUsd;
      expect(spent).toBe(0);
      const first = await c.characters.topUpEnergy("chr_seedHana", 5000);
      const e = await fail(c.characters.topUpEnergy("chr_seedHana", 5000));
      expect(e.code).toBe("daily_budget_exceeded");
      expect((await c.characters.get("chr_seedHana")).energy.current).toBe(first.current);
    });

    test("M2", "a top-up is recorded at $0 with its points and does not count as spend", async () => {
      const { c } = await make({ key: true });
      const before = (await c.settings.get()).spentTodayUsd;
      await c.characters.topUpEnergy("chr_seedHana", 500);
      const rows = await c.usage.list();
      const last = rows.filter((r) => r.category === "energy_topup").at(-1)!;
      expect(last).toMatchObject({ category: "energy_topup", energyPoints: 500, costUsd: 0, characterId: "chr_seedHana" });
      expect((await c.settings.get()).spentTodayUsd).toBe(before);
    });

    // ── rev 1.3: knowledge sources (knowledge-sources spec, D-65) ─────────────
    test("M5", "knowledge: CSV and links are rejected with validation; nothing is created", async () => {
      const { c } = await make();
      const before = (await c.characters.knowledge("chr_seedHana")).length;
      const e = await fail(c.characters.addKnowledge("chr_seedHana", { file: new File(["a,b\n1,2\n"], "sheet.csv", { type: "text/csv" }) }));
      expect(e.code).toBe("validation");
      expect(await code(c.characters.addKnowledge("chr_seedHana", { file: new File(["%PDF-1.7"], "notes.html", { type: "text/html" }) }))).toBe("validation");
      expect(await code(c.characters.addKnowledge("chr_seedHana", { file: new File(["not a pdf"], "fake.pdf", { type: "application/pdf" }) }))).toBe("validation");
      expect((await c.characters.knowledge("chr_seedHana")).length).toBe(before);
    });

    test("M5", "knowledge: pasted text is accepted as type text, status indexing, with kno_ id", async () => {
      const { c } = await make();
      const src = await c.characters.addKnowledge("chr_seedHana", { type: "text", title: "Notes", text: "Rice first.\n\nThen the fish." });
      expect(src).toMatchObject({ type: "text", status: "indexing", title: "Notes", characterId: "chr_seedHana", worldId: "wld_seedSunnyHollow" });
      expect(src.id).toMatch(/^kno_[0-9A-Za-z]{1,40}$/);
    });

    test("M5", "knowledge: files over 10 MB, a 21st source and duplicate content are refused", async () => {
      const { c } = await make();
      const big = new File([new Uint8Array(10 * 1024 * 1024 + 1)], "huge.txt", { type: "text/plain" });
      expect((await fail(c.characters.addKnowledge("chr_seedHana", { file: big }))).details).toMatchObject({ limit: 10 * 1024 * 1024 });
      const once = { file: new File(["Same words twice."], "same.md", { type: "text/markdown" }) };
      await c.characters.addKnowledge("chr_seedHana", once);
      expect(await code(c.characters.addKnowledge("chr_seedHana", { file: new File(["Same words twice."], "copy.md", { type: "text/markdown" }) }))).toBe("conflict");
      for (let n = (await c.characters.knowledge("chr_seedHana")).length; n < 20; n++) {
        await c.characters.addKnowledge("chr_seedHana", { type: "text", title: `Note ${n}`, text: `Recipe card number ${n}.` });
      }
      const e = await fail(c.characters.addKnowledge("chr_seedHana", { type: "text", title: "One more", text: "Overflow." }));
      expect(e.code).toBe("validation");
      expect(e.details?.limit).toBe(20);
    });

    test("M5", "knowledge: with a key, progress climbs through the stages and the source ends indexed with an embedding row", async () => {
      const { c, tick, globals } = await make({ key: true });
      const src = await c.characters.addKnowledge("chr_seedHana", { file: new File(["# Soups\n\nMiso first.\n\nThen tofu."], "soups.md", { type: "text/markdown" }) });
      await tick(5000);
      const progress = globals.flatMap((g) => (g.type === "entity.changed" && g.kind === "knowledge" && g.id === src.id && g.progress ? [g.progress] : []));
      expect(progress.length).toBeGreaterThanOrEqual(3);
      expect(progress.map((p) => p.pct)).toEqual([...progress.map((p) => p.pct)].sort((a, b) => a - b));
      expect(new Set(progress.map((p) => p.stage))).toEqual(new Set(["extracting", "chunking", "embedding"]));
      for (const g of globals) GlobalEventSchema.parse(g);
      const { source, chunks } = await c.characters.knowledgeSource(src.id);
      expect(source.status).toBe("indexed");
      expect(source.chunks).toBe(3);
      expect(chunks.map((k) => k.text)).toEqual(["# Soups", "Miso first.", "Then tofu."]);
      for (const k of chunks) KnowledgeChunkSchema.parse(k);
      const rows = (await c.usage.list()).filter((r) => r.category === "embedding" && r.characterId === "chr_seedHana");
      expect(rows.length).toBe(1);
      // Embedding is cheap ($0.01/M): a few short passages round to $0.000000, but the tokens are recorded.
      expect(rows[0].tokensIn).toBeGreaterThan(0);
      expect(rows[0].model).toBe((await c.settings.get()).models.embedding);
    });

    test("M5", "knowledge: without a key the source ends keyword_only, readable, with no ledger row; a key re-embeds it", async () => {
      const { c, tick, h } = await make();
      const src = await c.characters.addKnowledge("chr_seedHana", { type: "text", title: "Tea", text: "Steep for three minutes." });
      await tick(5000);
      let got = await c.characters.knowledgeSource(src.id);
      expect(got.source.status).toBe("keyword_only");
      expect(got.chunks.map((k) => k.text)).toEqual(["Steep for three minutes."]);
      expect((await c.usage.list()).some((r) => r.category === "embedding")).toBe(false);
      const ids = got.chunks.map((k) => k.id);
      // Saving a key embeds the user's keyword-only sources in the background; seed sources wait for their Index.
      await h.setKey();
      await tick(5000);
      got = await c.characters.knowledgeSource(src.id);
      expect(got.source.status).toBe("indexed");
      expect(got.chunks.map((k) => k.id)).toEqual(ids);
      expect((await c.usage.list()).filter((r) => r.category === "embedding").length).toBe(1);
    });

    test("M5", "knowledge: re-indexing a source that is still indexing rejects with conflict", async () => {
      const { c, tick } = await make({ key: true });
      // A PDF converts for a while (Docling on the backend; staged pacing in the mock), so it is still indexing here.
      const pdf = new File(["%PDF-1.7\n% notes\n"], "notes.pdf", { type: "application/pdf" });
      const src = await c.characters.addKnowledge("chr_seedHana", { file: pdf });
      expect(src.status).toBe("indexing");
      const e = await fail(c.characters.reindexKnowledge(src.id));
      expect(e.code).toBe("conflict");
      expect(e.retryable).toBe(false);
      await tick(5000);
      expect((await c.characters.knowledgeSource(src.id)).source.status).toBe("indexed");
      expect((await c.characters.reindexKnowledge(src.id)).status).toBe("indexing");
      await tick(5000);
    });

    test("M5", "knowledge: pasted text over 200 KB is refused with validation naming the limit", async () => {
      const { c } = await make();
      const before = (await c.characters.knowledge("chr_seedHana")).length;
      const e = await fail(c.characters.addKnowledge("chr_seedHana", { type: "text", title: "Long", text: "a".repeat(210 * 1024) }));
      expect(e.code).toBe("validation");
      expect(e.details?.limit).toBe(204800);
      expect((await c.characters.knowledge("chr_seedHana")).length).toBe(before);
    });

    test("M5", "memory: Forget removes the item and announces the change; an unknown id is not_found", async () => {
      const { c, globals } = await make();
      const items = await c.characters.memory("chr_seedHana");
      expect(items.length).toBeGreaterThan(0);
      const gone = items[0];
      await c.characters.forgetMemory(gone.id);
      expect((await c.characters.memory("chr_seedHana")).some((m) => m.id === gone.id)).toBe(false);
      await eventually(() => globals.some((g) => g.type === "entity.changed" && g.kind === "memory"));
      expect(await code(c.characters.forgetMemory(gone.id))).toBe("not_found");
      expect(await code(c.characters.forgetMemory("mem_nope"))).toBe("not_found");
    });

    test("M5", "knowledge: deleting a cited source removes it, but old transcripts keep their citations", async () => {
      const { c } = await make();
      const before = (await c.sessions.messages("ses_seedDebate4Day")).flatMap((m) => m.citations ?? []).filter((ct) => ct.sourceId === "kno_seedAmara1");
      expect(before.length).toBeGreaterThan(0);
      await c.characters.deleteKnowledge("kno_seedAmara1");
      expect(await code(c.characters.knowledgeSource("kno_seedAmara1"))).toBe("not_found");
      expect((await c.characters.knowledge("chr_seedAmara")).some((k) => k.id === "kno_seedAmara1")).toBe(false);
      const after = (await c.sessions.messages("ses_seedDebate4Day")).flatMap((m) => m.citations ?? []).filter((ct) => ct.sourceId === "kno_seedAmara1");
      expect(after).toEqual(before);
      expect(await code(c.characters.deleteKnowledge("kno_seedAmara1"))).toBe("not_found");
    });

    test("M5", "knowledge: re-indexing a seed source keeps its chunk ids, so citations still resolve", async () => {
      const { c, tick } = await make({ key: true });
      const ids = (await c.characters.knowledgeSource("kno_seedAmara1")).chunks.map((k) => k.id);
      await c.characters.reindexKnowledge("kno_seedAmara1");
      await tick(5000);
      const after = await c.characters.knowledgeSource("kno_seedAmara1");
      expect(after.source.status).toBe("indexed");
      expect(after.chunks.map((k) => k.id)).toEqual(ids);
    });

    // ── rev 1.3: world cover upload (worlds spec) ──────────────────────────────
    test("M4", "uploadCover: a PNG becomes an uploaded cover and the world change is announced", async () => {
      const { c, globals } = await make();
      // A real (tiny) PNG: the backend decodes and re-encodes the upload, so magic bytes alone aren't enough there.
      const png = new File([new Uint8Array(TINY_PNG)], "cover.png", { type: "image/png" });
      const w = await c.worlds.uploadCover("wld_seedMeridian", png);
      expect(w.cover.kind).toBe("upload");
      expect(w.cover.url?.length).toBeGreaterThan(0);
      expect((await c.worlds.get("wld_seedMeridian")).cover).toEqual(w.cover);
      expect(globals).toContainEqual(expect.objectContaining({ type: "entity.changed", kind: "world", id: "wld_seedMeridian" }));
    });

    test("M4", "uploadCover: a GIF, a fake PNG or a 6 MB JPEG is rejected with validation and the cover is unchanged", async () => {
      const { c } = await make();
      const before = (await c.worlds.get("wld_seedMeridian")).cover;
      const gif = new File([new Uint8Array([0x47, 0x49, 0x46, 0x38])], "a.gif", { type: "image/gif" });
      const fake = new File(["not really a png"], "b.png", { type: "image/png" });
      const big = new File([new Uint8Array([0xff, 0xd8, 0xff, ...new Array(6 * 1024 * 1024).fill(0)])], "c.jpg", { type: "image/jpeg" });
      for (const f of [gif, fake, big]) expect(await code(c.worlds.uploadCover("wld_seedMeridian", f)), f.name).toBe("validation");
      expect((await c.worlds.get("wld_seedMeridian")).cover).toEqual(before);
    });

    test("M4", "uploadCover: an unknown world rejects with not_found", async () => {
      const { c } = await make();
      const png = new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], "cover.png", { type: "image/png" });
      expect(await code(c.worlds.uploadCover("wld_nope", png))).toBe("not_found");
    });

    // ── rev 1.3: character lifecycle (character-lifecycle spec, D-70) ───────────
    test("M4", "delete leaves a readable tombstone; memory and knowledge go", async () => {
      const { c, globals } = await make();
      const before = await c.characters.get("chr_seedVictor");
      await c.characters.delete("chr_seedVictor");
      const t = await c.characters.get("chr_seedVictor");
      expect(t.deletedAt).toBeDefined();
      expect(t.profile.name).toBe(before.profile.name);
      expect(t.paletteId).toBe(before.paletteId);
      expect(t.emotions.neutral?.url).toBe(before.emotions.neutral?.url);
      CharacterSchema.parse(JSON.parse(JSON.stringify(t)));
      expect(await c.characters.memory("chr_seedVictor")).toEqual([]);
      expect(await c.characters.knowledge("chr_seedVictor")).toEqual([]);
      expect(globals).toContainEqual(expect.objectContaining({ type: "entity.changed", kind: "character", id: "chr_seedVictor" }));
    });

    test("M4", "tombstones leave the roster and the count, and every command on them is not_found", async () => {
      const { c } = await make({ key: true });
      const count = (await c.worlds.get("wld_seedMeridian")).characterCount;
      await c.characters.delete("chr_seedVictor");
      expect((await c.characters.list("wld_seedMeridian", { includeArchived: true })).some((x) => x.id === "chr_seedVictor")).toBe(false);
      expect((await c.worlds.get("wld_seedMeridian")).characterCount).toBe(count - 1);
      expect(await code(c.characters.update("chr_seedVictor", { advisory: true }))).toBe("not_found");
      expect(await code(c.jobs.start({ characterId: "chr_seedVictor", kind: "song" }))).toBe("not_found");
      expect(await code(c.characters.delete("chr_seedVictor"))).toBe("not_found");
      expect(await code(c.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedVictor"] }))).toBe("not_found");
    });

    test("M4", "transcripts with a deleted speaker still open, replay and export", async () => {
      const { c } = await make();
      const msgs = await c.sessions.messages("ses_seedDebate4Day");
      expect(msgs.some((m) => m.author.characterId === "chr_seedVictor")).toBe(true);
      await c.characters.delete("chr_seedVictor");
      const snap = await c.sessions.get("ses_seedDebate4Day");
      expect(snap.messages.length).toBe(msgs.length);
      expect((await c.sessions.events("ses_seedDebate4Day")).length).toBeGreaterThan(0);
      expect(await c.sessions.export("ses_seedDebate4Day")).toContain((await c.characters.get("chr_seedVictor")).profile.name);
    });

    test("M4", "deleting a character who is speaking in the live session is a conflict", async () => {
      const { c, tick } = await make({ key: true });
      const s = await c.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedVictor"] });
      await tick(6000);
      await c.chat.send(s.session.id, "Walk me through the whole case, step by step.");
      for (let i = 0; i < 40; i++) {
        await tick(250);
        if ((await c.sessions.messages(s.session.id)).some((m) => m.status === "streaming")) break;
      }
      const e = await fail(c.characters.delete("chr_seedVictor"));
      expect(e.code).toBe("conflict");
      expect((await c.characters.get("chr_seedVictor")).deletedAt).toBeUndefined();
    });

    // ── rev 1.3: Reset demo data keeps user data (demo-data spec, D-70) ─────────
    test("M4", "reset: a fork of a seed session survives, an edited seed character goes back to shipped", async () => {
      const { c, globals, reset } = await make({ key: true });
      const shipped = (await c.characters.get("chr_seedHana")).profile.tagline;
      const fork = await c.sessions.forkSeedSession("ses_seedHanaLongDay");
      await c.characters.update("chr_seedHana", { profile: { tagline: "Edited by the user" } });
      expect((await c.characters.get("chr_seedHana")).profile.tagline).toBe("Edited by the user");
      await reset();
      expect((await c.sessions.get(fork.session.id)).messages.length).toBe(fork.messages.length);
      expect((await c.characters.get("chr_seedHana")).profile.tagline).toBe(shipped);
      expect(globals.some((g) => g.type === "mock.reset")).toBe(true);
    });

    test("M4", "reset: a user-created world and its character are untouched", async () => {
      const { c, tick, reset } = await make({ key: true });
      const w = await c.worlds.create({ name: "My Street", cover: { kind: "preset", presetId: "cover_night_skyline" } });
      const { character } = await c.characters.createDraft(w.id, { seedPrompt: "Noor, a baker", intent: "companion" });
      await tick(5000);
      const before = await c.characters.get(character.id);
      await reset();
      expect((await c.worlds.get(w.id)).name).toBe("My Street");
      expect(await c.characters.get(character.id)).toEqual(before);
      expect((await c.worlds.list()).length).toBe(3);
    });

    // ── M1b (backend-foundation): worlds, demo reset and replay over any client ─
    test("M1b", "worlds: create, rename and delete", async () => {
      const { c, globals } = await make();
      const w = await c.worlds.create({ name: "  My Street  ", cover: COVER });
      expect(w).toMatchObject({ name: "My Street", isSeed: false, characterCount: 0 });
      expect((await c.worlds.list())[0].id).toBe(w.id);
      expect((await c.worlds.update(w.id, { name: "Elm Street" })).name).toBe("Elm Street");
      await c.worlds.delete(w.id);
      expect(await code(c.worlds.get(w.id))).toBe("not_found");
      expect(await code(c.worlds.update("wld_nope", { name: "X" }))).toBe("not_found");
      await eventually(() => globals.some((g) => g.type === "entity.changed" && g.kind === "world" && g.id === w.id));
    });

    test("M1b", "worlds: duplicate and reserved names are refused with conflict", async () => {
      const { c } = await make();
      await c.worlds.create({ name: "My Street", cover: COVER });
      const dup = await fail(c.worlds.create({ name: "my street ", cover: COVER }));
      expect([dup.code, dup.details?.field]).toEqual(["conflict", "name"]);
      await c.worlds.update("wld_seedMeridian", { name: "Council B" });
      const taken = await fail(c.worlds.create({ name: "Meridian Council", cover: COVER }));
      expect([taken.code, taken.details?.field]).toEqual(["conflict", "name"]);
    });

    // Promoted from the mock-only checks in M6 (http-client-parity G6): the backend implements the same name rules.
    test("M1b", "worlds: a world keeps its own name; a seed world takes its shipped name back, case-insensitively", async () => {
      const { c } = await make();
      const w = await c.worlds.create({ name: "  My Street ", cover: COVER });
      expect((await c.worlds.update(w.id, { name: "My Street" })).name).toBe("My Street");
      await c.worlds.update("wld_seedMeridian", { name: "Council B" });
      const taken = await fail(c.worlds.create({ name: "MERIDIAN COUNCIL", cover: COVER }));
      expect([taken.code, taken.details?.field]).toEqual(["conflict", "name"]);
      expect((await c.worlds.update("wld_seedMeridian", { name: "Meridian Council" })).name).toBe("Meridian Council");
    });

    test("M1b", "reset: a renamed and a deleted seed world come back; a user world stays", async () => {
      const { c, globals, reset } = await make();
      const mine = await c.worlds.create({ name: "My Street", cover: COVER });
      await c.worlds.update("wld_seedMeridian", { name: "Council B" });
      await c.worlds.delete("wld_seedSunnyHollow");
      await reset();
      const names = Object.fromEntries((await c.worlds.list()).map((w) => [w.id, w.name]));
      expect(names).toMatchObject({ wld_seedMeridian: "Meridian Council", wld_seedSunnyHollow: "Sunny Hollow", [mine.id]: "My Street" });
      expect((await c.sessions.list("wld_seedSunnyHollow")).some((s) => s.id === "ses_seedDinner")).toBe(true);
      await eventually(() => globals.some((g) => g.type === "mock.reset"));
    });

    test("M1b", "subscribe(sinceSeq) on a seed recording replays exactly the stored events above it", async () => {
      const { c } = await make();
      const sid = "ses_seedAmaraHeadache";
      const want = (await c.sessions.events(sid)).filter((e) => e.seq > 3).map((e) => e.seq);
      const got: number[] = [];
      const unsub = c.sessions.subscribe(sid, { sinceSeq: 3 }, (e) => {
        SessionEventSchema.parse(e);
        got.push(e.seq);
      });
      await eventually(() => got.length >= want.length);
      unsub();
      expect(got).toEqual(want);
    });

    test("M1b", "every seed session's session and messages are the reduction of its events", async () => {
      const { c } = await make();
      let checked = 0;
      for (const w of await c.worlds.list()) {
        for (const s of (await c.sessions.list(w.id)).filter((x) => x.isSeed)) {
          const snap = await c.sessions.get(s.id);
          const events = await c.sessions.events(s.id);
          expect(snap.lastSeq).toBe(events.at(-1)?.seq ?? 0);
          const final = reduceAll(initialRuntime(seedBase(snap.session)), events);
          expect(JSON.parse(JSON.stringify(orderedMessages(final)))).toEqual(await c.sessions.messages(s.id));
          expect(JSON.parse(JSON.stringify(final.session))).toEqual(snap.session);
          checked += 1;
        }
      }
      expect(checked).toBe(5);
    });
  });
}
