// HttpClient unit tests (http-client spec): errors, idempotency keys, paging, streams and the not-yet methods,
// against a stubbed fetch and a fake EventSource. The end-to-end run is clientContract.http.test.ts. Owner: SWE.
import { describe, expect, it } from "vitest";
import { HorizonError } from "../../contract/errors";
import type { SessionEvent } from "../../contract/types";
import type { HorizonClient } from "../HorizonClient";
import { HttpClient } from "./HttpClient";
import type { EventSourceLike } from "./sse";

type Call = { url: string; init?: RequestInit };
const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } });

function stub(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const calls: Call[] = [];
  const fetch = async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    return handler(url, init);
  };
  return { calls, fetch };
}

class FakeES implements EventSourceLike {
  static all: FakeES[] = [];
  onmessage: ((e: MessageEvent) => void) | null = null;
  closed = false;
  private listeners = new Map<string, ((e: Event) => void)[]>();
  readonly url: string;
  constructor(url: string) {
    this.url = url;
    FakeES.all.push(this);
  }
  addEventListener(type: string, fn: (e: Event) => void): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), fn]);
  }
  close(): void { this.closed = true; }
  emit(type: string, data: unknown): void {
    const e = { data: JSON.stringify(data) } as MessageEvent;
    if (type === "message") this.onmessage?.(e);
    for (const fn of this.listeners.get(type) ?? []) fn(e);
  }
}
const open = () => FakeES.all.filter((e) => !e.closed);

const evt = (seq: number, sessionId = "ses_a"): SessionEvent =>
  ({ id: `evt_${seq}`, sessionId, seq, at: "2026-10-03T03:00:00.000Z", type: "session.resumed", payload: {} } as SessionEvent);

function make(handler: Parameters<typeof stub>[0], keys: string[] = []) {
  const s = stub(handler);
  let k = 0;
  const c = new HttpClient({ baseUrl: "http://h/api/v1", fetch: s.fetch, EventSource: FakeES, newKey: () => keys[k++] ?? `key-${k}` });
  return { c, calls: s.calls };
}

describe("HttpClient", () => {
  it("parses the error envelope into a HorizonError, details included", async () => {
    const { c } = make(() => json(409, { error: { code: "conflict", message: "A world with that name already exists.", retryable: false, details: { field: "name" } } }));
    const e = await c.worlds.create({ name: "x", cover: { kind: "preset" } }).catch((x: unknown) => x);
    expect(e).toBeInstanceOf(HorizonError);
    expect(e).toMatchObject({ code: "conflict", retryable: false, details: { field: "name" } });
  });

  it("an unreachable server is `network` and retryable", async () => {
    const { c } = make(() => { throw new TypeError("fetch failed"); });
    const e = (await c.worlds.list().catch((x: unknown) => x)) as HorizonError;
    expect(e.code).toBe("network");
    expect(e.retryable).toBe(true);
  });

  it("an envelope-less error still maps by status", async () => {
    const { c } = make(() => new Response("gateway down", { status: 504 }));
    expect(((await c.worlds.list().catch((x: unknown) => x)) as HorizonError).code).toBe("timeout");
  });

  it("every POST carries a fresh Idempotency-Key, and the network retry reuses it", async () => {
    let n = 0;
    const { c, calls } = make(() => {
      n += 1;
      if (n === 2) throw new TypeError("connection reset");
      return json(201, { id: "wld_a" });
    }, ["k1", "k2"]);
    await c.worlds.create({ name: "A", cover: { kind: "preset" } });
    await c.worlds.create({ name: "B", cover: { kind: "preset" } });
    const keys = calls.map((x) => ((x.init?.headers ?? {}) as Record<string, string>)["Idempotency-Key"]);
    expect(keys).toEqual(["k1", "k2", "k2"]);
  });

  it("follows nextCursor until null and returns every item in order", async () => {
    const pages: Record<string, unknown> = {
      "": { items: [evt(1), evt(2)], nextCursor: "c2" },
      c2: { items: [evt(3)], nextCursor: "c3" },
      c3: { items: [evt(4)], nextCursor: null },
    };
    const { c, calls } = make((url) => json(200, pages[new URL(url).searchParams.get("cursor") ?? ""]));
    expect((await c.sessions.events("ses_a")).map((e) => e.seq)).toEqual([1, 2, 3, 4]);
    expect(calls.every((x) => x.url.includes("limit=1000"))).toBe(true);
  });

  it("nothing is held back in M5: the knowledge and memory methods send their requests", async () => {
    const src = { id: "kno_a", characterId: "chr_a", title: "notes.md", type: "md", status: "indexing", chunks: 0, addedAt: "2026-10-03T03:00:00.000Z" };
    const { c, calls } = make((_url, init) => (init?.method === "DELETE" ? new Response(null, { status: 204 }) : json(201, src)));
    const file = new File(["# Notes\n\nBees."], "notes.md", { type: "text/markdown" });
    expect(await c.characters.addKnowledge("chr_seedHana", { file })).toEqual(src);
    expect(await c.characters.addKnowledge("chr_seedHana", { type: "text", title: "t", text: "x" })).toEqual(src);
    expect(await c.characters.reindexKnowledge("kno_a")).toEqual(src);
    expect(await c.characters.deleteKnowledge("kno_a")).toBeUndefined();
    expect(await c.characters.forgetMemory("mem_a")).toBeUndefined();
    const seen = calls.map((x) => [x.init?.method, x.url.replace(/^.*\/api\/v1/, "")]);
    expect(seen).toEqual([
      ["POST", "/characters/chr_seedHana/knowledge"],
      ["POST", "/characters/chr_seedHana/knowledge"],
      ["POST", "/knowledge/kno_a/reindex"],
      ["DELETE", "/knowledge/kno_a"],
      ["DELETE", "/memory/mem_a"],
    ]);
    const headers = (i: number) => new Headers(calls[i].init?.headers);
    expect(calls[0].init?.body).toBeInstanceOf(FormData);
    expect(((calls[0].init?.body as FormData).get("file") as File).name).toBe("notes.md");
    expect(JSON.parse(String(calls[1].init?.body))).toEqual({ type: "text", title: "t", text: "x" });
    for (const i of [0, 1, 2]) expect(headers(i).get("Idempotency-Key"), String(i)).toBeTruthy();
    expect(headers(3).get("Idempotency-Key")).toBeNull();
  });

  it("M2 settings and energy methods call their routes (no longer pending)", async () => {
    const energy = { max: 1000, current: 600, asOf: "2026-10-03T03:00:00.000Z", regenPerHour: 41.67, state: "active", spentToday: 0 };
    const { c, calls } = make((url) => json(200, url.includes("/energy/") ? energy : url.includes("test-") ? { ok: true, latencyMs: 9 } : {}));
    await c.settings.setKey("sk-or-test-0001");
    await c.settings.setKey(null);
    await c.settings.update({ budget: { dailyCapUsd: 0.6 } });
    await c.settings.testConnection();
    await c.settings.testModel("embedding");
    expect(await c.characters.topUpEnergy("chr_a", 500)).toEqual(energy);
    await c.characters.setEnergyMax("chr_a", 800);
    const seen = calls.map((x) => [x.init?.method, x.url.replace(/^.*\/api\/v1/, ""), x.init?.body ?? null]);
    expect(seen).toEqual([
      ["PUT", "/settings/key", JSON.stringify({ key: "sk-or-test-0001" })],
      ["PUT", "/settings/key", JSON.stringify({ key: null })],
      ["PATCH", "/settings", JSON.stringify({ budget: { dailyCapUsd: 0.6 } })],
      ["POST", "/settings/test-connection", null],
      ["POST", "/settings/test-model", JSON.stringify({ role: "embedding" })],
      ["POST", "/characters/chr_a/energy/top-up", JSON.stringify({ points: 500 })],
      ["PUT", "/characters/chr_a/energy/max", JSON.stringify({ points: 800 })],
    ]);
    const headers = (i: number) => calls[i].init?.headers as Record<string, string>;
    expect(headers(5)["Idempotency-Key"]).toBeTruthy(); // the top-up POST
    expect(headers(0)["Idempotency-Key"]).toBeUndefined(); // PUTs are naturally idempotent
  });

  it("M3 session methods call their routes; POSTs carry an Idempotency-Key", async () => {
    const snap = { session: { id: "ses_n" }, messages: [], lastSeq: 2 };
    const md = ["# Title", "", "**You**: hi"].join("\n");
    const { c, calls } = make((url, init) => {
      if (url.endsWith("/export")) return new Response(md, { status: 200, headers: { "content-type": "text/markdown" } });
      if (init?.method === "DELETE" || url.endsWith("/leave") || url.endsWith("/end")) return new Response(null, { status: 204 });
      if (init?.method === "PATCH") return json(200, { id: "ses_n", title: "New" });
      return json(201, snap);
    });
    expect(await c.sessions.create({ worldId: "wld_a", mode: "one_on_one", characterIds: ["chr_a"] })).toEqual(snap);
    expect(await c.sessions.forkSeedSession("ses_seed", 12)).toEqual(snap);
    await c.sessions.forkSeedSession("ses_seed");
    expect((await c.sessions.rename("ses_n", "New")).title).toBe("New");
    expect(await c.sessions.export("ses_n")).toBe(md);
    await c.sessions.leave("ses_n");
    await c.sessions.end("ses_n");
    await c.sessions.delete("ses_n");
    const seen = calls.map((x) => [x.init?.method, x.url.replace(/^.*\/api\/v1/, ""), x.init?.body ?? null]);
    expect(seen).toEqual([
      ["POST", "/sessions", JSON.stringify({ worldId: "wld_a", mode: "one_on_one", characterIds: ["chr_a"] })],
      ["POST", "/sessions/ses_seed/fork", JSON.stringify({ atSeq: 12 })],
      ["POST", "/sessions/ses_seed/fork", JSON.stringify({})],
      ["PATCH", "/sessions/ses_n", JSON.stringify({ title: "New" })],
      ["GET", "/sessions/ses_n/export", null],
      ["POST", "/sessions/ses_n/leave", null],
      ["POST", "/sessions/ses_n/end", null],
      ["DELETE", "/sessions/ses_n", null],
    ]);
    const posts = calls.filter((x) => x.init?.method === "POST");
    expect(posts.every((x) => ((x.init?.headers ?? {}) as Record<string, string>)["Idempotency-Key"])).toBe(true);
  });

  it("send over HTTP: one POST with an Idempotency-Key, resolving on 202", async () => {
    const { c, calls } = make(() => json(202, {}), ["send-key"]);
    await expect(c.chat.send("ses_a", "hello", { mentions: ["chr_b"] })).resolves.toBeUndefined();
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("http://h/api/v1/sessions/ses_a/send");
    expect(calls[0].init?.body).toBe(JSON.stringify({ text: "hello", mentions: ["chr_b"] }));
    expect(((calls[0].init?.headers ?? {}) as Record<string, string>)["Idempotency-Key"]).toBe("send-key");
  });

  it("every chat, debate and watch command posts to its route", async () => {
    const { c, calls } = make(() => json(202, {}));
    await c.chat.stop("s");
    await c.chat.regenerate("s", "msg_a");
    await c.chat.setEmotion("s", "chr_a", "happy");
    await c.chat.setEmotionMode("s", "user");
    await c.chat.setResponderPolicy("s", "everyone");
    await c.chat.setMusicPolicy("s", "arena");
    await c.chat.setReadableMode("s", true);
    await c.chat.everyoneAnswer("s");
    await c.chat.nextSpeaker("s");
    await c.chat.nextSpeaker("s", "chr_a");
    await c.chat.muteParticipant("s", "chr_a", true);
    await c.debate.pause("s");
    await c.debate.resume("s");
    await c.debate.next("s");
    await c.debate.setAutoAdvance("s", false);
    await c.debate.askCharacter("s", "chr_a", "why?");
    await c.debate.interject("s", "hm");
    await c.debate.extendRound("s");
    await c.debate.skipToClosing("s");
    await c.debate.endDebate("s", true);
    await c.debate.pickStrongerCase("s", "prop");
    await c.watch.play("s");
    await c.watch.pause("s");
    await c.watch.step("s");
    await c.watch.setPace("s", 500);
    await c.watch.direct("s", "rain");
    await c.watch.stepIn("s", "hi");
    await c.watch.extendWatch("s");
    await c.watch.extendWatch("s", 5);
    await c.watch.summarise("s");
    const seen = calls.map((x) => `${x.url.replace(/^.*\/sessions\/s\//, "")} ${x.init?.body ?? ""}`);
    expect(seen).toEqual([
      "stop {}", 'regenerate {"messageId":"msg_a"}', 'set-emotion {"characterId":"chr_a","emotion":"happy"}',
      'set-emotion-mode {"mode":"user"}', 'set-responder-policy {"policy":"everyone"}', 'set-music-policy {"policy":"arena"}',
      'set-readable-mode {"on":true}', "everyone-answer {}", "next-speaker {}", 'next-speaker {"characterId":"chr_a"}',
      'mute {"characterId":"chr_a","muted":true}', "debate/pause {}", "debate/resume {}", "debate/next {}",
      'debate/auto-advance {"on":false}', 'debate/ask {"characterId":"chr_a","text":"why?"}', 'debate/interject {"text":"hm"}',
      "debate/extend-round {}", "debate/skip-to-closing {}", 'debate/end {"withVerdict":true}', 'debate/pick {"side":"prop"}',
      "watch/play {}", "watch/pause {}", "watch/step {}", 'watch/pace {"paceMs":500}', 'watch/direct {"text":"rain"}',
      'watch/step-in {"text":"hi"}', "watch/extend {}", 'watch/extend {"turns":5}', "watch/summarise {}",
    ]);
  });

  it("a refused create surfaces conflict with details.activeSessionId", async () => {
    const { c } = make(() => json(409, { error: { code: "conflict", message: "Another session is live. Leave it first.", retryable: false, details: { activeSessionId: "ses_live" } } }));
    const e = (await c.sessions.create({ worldId: "wld_a", mode: "one_on_one", characterIds: ["chr_a"] }).catch((x: unknown) => x)) as HorizonError;
    expect(e).toBeInstanceOf(HorizonError);
    expect([e.code, e.details?.activeSessionId]).toEqual(["conflict", "ses_live"]);
  });

  it("a refused top-up maps to daily_budget_exceeded", async () => {
    const { c } = make(() => json(402, { error: { code: "daily_budget_exceeded", message: "Top-ups are bounded by today's budget.", retryable: false, details: { todayTopUpPoints: 5000, points: 5000 } } }));
    const e = (await c.characters.topUpEnergy("chr_a", 5000).catch((x: unknown) => x)) as HorizonError;
    expect(e).toBeInstanceOf(HorizonError);
    expect([e.code, e.details?.points]).toEqual(["daily_budget_exceeded", 5000]);
  });

  it("onGlobal shares one EventSource; the last unsubscribe closes it", () => {
    FakeES.all = [];
    const { c } = make(() => json(200, {}));
    const got: string[][] = [[], [], []];
    const unsubs = got.map((g) => c.onGlobal((e) => g.push(e.type)));
    expect(open()).toHaveLength(1);
    open()[0].emit("message", { type: "mock.reset" });
    expect(got).toEqual([["mock.reset"], ["mock.reset"], ["mock.reset"]]);
    unsubs.forEach((u) => u());
    expect(open()).toHaveLength(0);
  });

  it("a session stream delivers each seq once, and another session closes it (≤ 2 EventSources)", () => {
    FakeES.all = [];
    const { c } = make(() => json(200, {}));
    const seen: number[] = [];
    c.onGlobal(() => undefined);
    c.sessions.subscribe("ses_a", { sinceSeq: 0 }, (e) => seen.push(e.seq));
    const es = FakeES.all[1];
    expect(es.url).toBe("http://h/api/v1/sessions/ses_a/stream?sinceSeq=0");
    for (const s of [1, 2, 2, 3, 1]) es.emit("session.resumed", evt(s)); // a reconnect replays 2 and 1
    expect(seen).toEqual([1, 2, 3]);
    c.sessions.subscribe("ses_b", { sinceSeq: 0 }, () => undefined);
    expect(es.closed).toBe(true);
    expect((c as HttpClient).openStreams).toBe(2);
    expect(open()).toHaveLength(2);
  });

  it("a second subscriber on the same session gets its backlog first, then live events, without gaps", async () => {
    FakeES.all = [];
    const { c } = make(() => json(200, { items: [evt(1), evt(2), evt(3)], nextCursor: null }));
    const a: number[] = [];
    const b: number[] = [];
    c.sessions.subscribe("ses_a", { sinceSeq: 2 }, (e) => a.push(e.seq));
    const es = FakeES.all[0];
    es.emit("session.resumed", evt(3));
    c.sessions.subscribe("ses_a", { sinceSeq: 0 }, (e) => b.push(e.seq));
    es.emit("session.resumed", evt(4)); // arrives while b's backlog is still loading
    await new Promise((r) => setTimeout(r, 0));
    expect(a).toEqual([3, 4]);
    expect(b).toEqual([1, 2, 3, 4]);
    expect(FakeES.all).toHaveLength(1);
  });

  it("jobs.subscribe = a snapshot, then the global stream filtered by jobId", async () => {
    FakeES.all = [];
    const job = { id: "job_a", status: "running" };
    const { c } = make(() => json(200, job));
    const seen: string[] = [];
    (c as HorizonClient).jobs.subscribe("job_a", (e) => seen.push(e.type));
    await new Promise((r) => setTimeout(r, 0));
    const es = FakeES.all[0];
    es.emit("message", { type: "task.update", jobId: "job_other", task: {} });
    es.emit("message", { type: "task.update", jobId: "job_a", task: {} });
    es.emit("message", { type: "job.done", job: { ...job, status: "succeeded" } });
    expect(seen).toEqual(["job.progress", "task.update", "job.done"]);
  });

  it("M4: uploadCover is one multipart POST with an Idempotency-Key", async () => {
    const world = { id: "wld_a", name: "A", cover: { kind: "upload", url: "/assets/gen/wld_a/cover_v1.webp" } };
    const { c, calls } = make(() => json(200, world), ["k-cover"]);
    const png = new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], "cover.png", { type: "image/png" });
    const w = await c.worlds.uploadCover("wld_a", png);
    expect(w.cover).toEqual({ kind: "upload", url: "/assets/gen/wld_a/cover_v1.webp" });
    expect(calls).toHaveLength(1);
    const { url, init } = calls[0];
    expect([url, init?.method]).toEqual(["http://h/api/v1/worlds/wld_a/cover", "POST"]);
    const headers = init?.headers as Record<string, string>;
    expect(headers["Idempotency-Key"]).toBe("k-cover");
    expect(headers["Content-Type"]).toBeUndefined();   // fetch sets the multipart boundary
    const form = init?.body as FormData;
    expect(form).toBeInstanceOf(FormData);
    expect((form.get("file") as File).name).toBe("cover.png");
  });

  it("M4: jobs.start is one POST /jobs; subscribe gets its task.update and job.done from the global stream", async () => {
    FakeES.all = [];
    const job = { id: "job_p", characterId: "chr_a", kind: "portrait_candidates", status: "queued", tasks: [] };
    const { c, calls } = make(() => json(201, job), ["k-job"]);
    const started = await c.jobs.start({ characterId: "chr_a", kind: "portrait_candidates" });
    expect(started.id).toBe("job_p");
    const sent = calls[0].init?.headers as Record<string, string> | undefined;
    expect([calls[0].url, calls[0].init?.method, sent?.["Idempotency-Key"]]).toEqual(["http://h/api/v1/jobs", "POST", "k-job"]);
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ characterId: "chr_a", kind: "portrait_candidates" });
    const seen: string[] = [];
    c.jobs.subscribe("job_p", (e) => seen.push(e.type));
    await new Promise((r) => setTimeout(r, 0));
    const es = FakeES.all[0];
    es.emit("message", { type: "task.update", jobId: "job_p", task: { id: "task_1", status: "running" } });
    es.emit("message", { type: "job.done", job: { ...job, status: "succeeded" } });
    expect(seen).toEqual(["job.progress", "task.update", "job.done"]);
  });

  it("M4: the character and job routes", async () => {
    const { c, calls } = make((url) => json(url.endsWith("/delete") ? 204 : 200, url.includes("/jobs") ? { id: "job_a" } : { id: "chr_a" }));
    await c.characters.createDraft("wld_a", { seedPrompt: "Sarah, a doctor", intent: "expert" });
    await c.characters.update("chr_a", { profile: { tagline: "x" } });
    await c.characters.lockPortrait("chr_a", "cand_1");
    await c.characters.approve("chr_a");
    await c.characters.archive("chr_a");
    await c.characters.restore("chr_a");
    await c.characters.acceptAssetVersion("emo_1");
    await c.jobs.estimate({ characterId: "chr_a", kind: "song" });
    await c.jobs.cancel("job_a");
    await c.jobs.retryTask("job_a", "task_1");
    expect(calls.map((x) => `${x.init?.method} ${x.url.replace("http://h/api/v1", "")}`)).toEqual([
      "POST /worlds/wld_a/characters", "PATCH /characters/chr_a", "POST /characters/chr_a/lock-portrait",
      "POST /characters/chr_a/approve", "POST /characters/chr_a/archive", "POST /characters/chr_a/restore",
      "POST /assets/emo_1/accept", "POST /jobs/estimate", "POST /jobs/job_a/cancel", "POST /jobs/job_a/tasks/task_1/retry",
    ]);
  });
});
