// HorizonClient contract (EE paper §2.10): the executable spec SWE's HttpClient must also pass.
// Runs against MockClient on a ManualClock (deterministic, no wall time). Owner: EE.
import { beforeAll, describe, expect, it } from "vitest";
import type { Message, SessionEvent } from "../contract/types";
import { HorizonError } from "../contract/errors";
import type { Dataset } from "../mock/db/dataset";
import { loadSeedDataset } from "../mock/db/loadSeed";
import { MockClient } from "../mock/MockClient";
import { ManualClock } from "../mock/time/Clock";
import type { GlobalEvent, JobEvent } from "./HorizonClient";

// Saturday 11:00 MYT: off-peak, so energy maths are the base rate.
const START = Date.parse("2026-10-03T03:00:00Z");
let seed: Dataset;
beforeAll(async () => {
  seed = await loadSeedDataset();
});

async function make(opts: { key?: boolean; speed?: 1 | 2 | 4 } = {}) {
  const clock = new ManualClock(START);
  const c = new MockClient({ clock, storage: null, dataset: seed, speed: opts.speed });
  await c.ready;
  if (opts.key) await c.settings.setKey("sk-or-test-0001");
  const events: SessionEvent[] = [];
  const globals: GlobalEvent[] = [];
  c.onGlobal((e) => globals.push(e));
  const tick = async (ms: number) => {
    for (let t = 0; t < ms; t += 250) {
      clock.advance(Math.min(250, ms - t));
      await Promise.resolve();
    }
    await new Promise((r) => setTimeout(r, 0));
  };
  const watch = (sid: string) => c.sessions.subscribe(sid, { sinceSeq: 0 }, (e) => events.push(e));
  return { c, clock, tick, events, globals, watch };
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
const chars = (msgs: Message[]) => msgs.filter((m) => m.author.type === "character");

describe("HorizonClient contract (MockClient)", () => {
  it("queries work without a key; live actions reject with missing_key (R15 demo mode)", async () => {
    const { c } = await make();
    expect((await c.settings.get()).openRouterKeyStatus).toBe("missing");
    const worlds = await c.worlds.list();
    expect(worlds.map((w) => w.id).sort()).toEqual(["wld_seedMeridian", "wld_seedSunnyHollow"]);
    expect(worlds.find((w) => w.id === "wld_seedMeridian")?.characterCount).toBeGreaterThanOrEqual(3);
    const roster = await c.characters.list("wld_seedSunnyHollow");
    expect(roster.some((x) => x.status === "archived")).toBe(false);
    expect((await c.characters.list("wld_seedSunnyHollow", { includeArchived: true })).some((x) => x.status === "archived")).toBe(true);
    expect((await c.sessions.list("wld_seedMeridian")).length).toBeGreaterThanOrEqual(5);
    expect(await code(c.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedAmara"] }))).toBe("missing_key");
    expect(await code(c.jobs.start({ characterId: "chr_mockSarah", kind: "portrait_candidates" }))).toBe("missing_key");
  });

  it("mock keys: sk-or-* valid, sk-or-bad* invalid", async () => {
    const { c } = await make();
    expect((await c.settings.setKey("sk-or-bad-zzz")).openRouterKeyStatus).toBe("invalid");
    expect(await code(c.settings.testConnection())).toBe("invalid_key");
    const s = await c.settings.setKey("sk-or-good");
    expect(s.openRouterKeyStatus).toBe("set");
    expect(s.demoMode).toBe(false);
    expect((await c.settings.testConnection()).ok).toBe(true);
  });

  it("1:1: greeting, then send → user message, streamed reply, energy drain, ledger row", async () => {
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
    const types = new Set(events.map((e) => e.type));
    for (const t of ["turn.next", "turn.thinking", "turn.start", "token", "emotion", "turn.end", "energy", "insight", "message"]) expect(types.has(t as SessionEvent["type"]), t).toBe(true);
    for (let i = 1; i < events.length; i++) expect(events[i].seq).toBe(events[i - 1].seq + 1);
    const after = (await c.characters.get("chr_seedAmara")).energy.current;
    expect(after).toBeLessThan(before);
    expect((await c.usage.summary()).byCategory.chat).toBeGreaterThan(0);
  });

  it("subscribe(sinceSeq) replays the backlog without gaps or duplicates", async () => {
    const { c, tick } = await make({ key: true });
    const snap = await c.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedMei"] });
    await tick(6000);
    const all = await c.sessions.events(snap.session.id);
    const got: number[] = [];
    c.sessions.subscribe(snap.session.id, { sinceSeq: 3 }, (e) => got.push(e.seq));
    await tick(10);
    expect(got).toEqual(all.filter((e) => e.seq > 3).map((e) => e.seq));
  });

  it("seed sessions are replay-only; forkSeedSession(atSeq) continues live from the playhead (R16)", async () => {
    const { c, tick } = await make({ key: true });
    expect(await code(c.chat.send("ses_seedAmaraHeadache", "hi"))).toBe("provider_error");
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

  it("debate (quick, arbiter) runs to a verdict and ends", async () => {
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

  it("watch stops at the turn cap with turn_cap; Continue +10 extends it", async () => {
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

  it("group: @mentioning an exhausted character gives an asleep note + energy_exhausted (ENG-04)", async () => {
    const { c, tick, events, watch } = await make({ key: true });
    await c.dev.setScenario("character_exhausted");
    const s = await c.sessions.create({ worldId: "wld_seedSunnyHollow", mode: "group", characterIds: ["chr_seedHana", "chr_seedTakeshi"] });
    watch(s.session.id);
    await c.chat.send(s.session.id, "Dad, dinner?", { mentions: ["chr_seedTakeshi"] });
    await tick(15000);
    const msgs = await c.sessions.messages(s.session.id);
    expect(msgs.some((m) => m.kind === "system_note" && /Takeshi is asleep/.test(m.content))).toBe(true);
    expect(events.some((e) => e.type === "error" && (e.payload as { code: string }).code === "energy_exhausted")).toBe(true);
    expect(chars(msgs).every((m) => m.author.characterId !== "chr_seedTakeshi")).toBe(true);
    await c.characters.topUpEnergy("chr_seedTakeshi", 500);
    expect((await c.characters.get("chr_seedTakeshi")).energy.current).toBe(500);
  });

  it("stream cut: error(network) then turn.end(interrupted)", async () => {
    const { c, tick } = await make({ key: true });
    const s = await c.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedVictor"] });
    await tick(6000);
    await c.dev.setScenario("stream_cut");
    await c.chat.send(s.session.id, "Define your terms, counsel. What exactly do you mean by a fair trial in this case?");
    await tick(12000);
    const last = chars(await c.sessions.messages(s.session.id)).at(-1)!;
    expect(last.status).toBe("interrupted");
    expect(last.error?.code).toBe("network");
  });

  it("Stop interrupts a streaming reply (interruptedBy user)", async () => {
    const { c, tick } = await make({ key: true });
    const s = await c.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedVictor"] });
    await tick(6000);
    await c.chat.send(s.session.id, "Tell me everything about precedent.");
    await tick(2000);
    await c.chat.stop(s.session.id);
    await tick(1000);
    const last = chars(await c.sessions.messages(s.session.id)).at(-1)!;
    expect(last.status).toBe("interrupted");
    expect(last.interruptedBy).toBe("user");
  });

  it("daily cap: spend reaching the cap pauses the session and blocks further sends (STATE-06)", async () => {
    const { c, tick, globals } = await make({ key: true });
    await c.settings.update({ budget: { dailyCapUsd: 0.00005 } });
    const s = await c.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedAmara"] });
    await tick(8000);
    expect(globals.some((g) => g.type === "budget.reached")).toBe(true);
    expect((await c.sessions.get(s.session.id)).session.pausedReason).toBe("daily_budget");
    expect(await code(c.chat.send(s.session.id, "hello?"))).toBe("daily_budget_exceeded");
  });

  it("creation pipeline: draft → profile job → portrait candidate → lock → emotions (Lean)", async () => {
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
    expect(cand.url.startsWith("data:image/svg+xml")).toBe(true);
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

  it("partial image failure: task 2 fails at 60 %, Retry succeeds (F6)", async () => {
    const { c, tick } = await make({ key: true });
    await c.settings.update({ generationMode: "standard" });
    await c.dev.setScenario("image_fail_partial");
    const job = await c.jobs.start({ characterId: "chr_mockSarah", kind: "portrait_candidates" });
    await tick(25000);
    const done = await c.jobs.get(job.id);
    expect(done.status).toBe("partial");
    const failed = done.tasks.find((t) => t.status === "failed")!;
    await c.jobs.retryTask(job.id, failed.id);
    await tick(25000);
    expect((await c.jobs.get(job.id)).status).toBe("succeeded");
  });

  it("network down rejects queries too; Reset demo data restores the shipped fixtures", async () => {
    const { c, globals } = await make({ key: true });
    await c.dev.setScenario("network_down");
    expect(await code(c.worlds.list())).toBe("network");
    await c.dev.setScenario("no_worlds");
    expect(await c.worlds.list()).toEqual([]);
    await c.dev.resetDemoData();
    expect((await c.worlds.list()).length).toBe(2);
    expect(globals.filter((g) => g.type === "mock.reset").length).toBeGreaterThanOrEqual(2);
  });

  it("demo speed ×4 compresses mock time", async () => {
    const { c, tick } = await make({ key: true, speed: 4 });
    const s = await c.sessions.create({ worldId: "wld_seedMeridian", mode: "one_on_one", characterIds: ["chr_seedAmara"] });
    await tick(1500);
    expect(chars(await c.sessions.messages(s.session.id))[0]?.status).toBe("complete");
  });
});
