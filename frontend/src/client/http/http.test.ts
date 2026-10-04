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

  it("methods without a backend yet reject with validation + availableIn, without a request", async () => {
    const { c, calls } = make(() => json(200, {}));
    const notYet: [string, () => Promise<unknown>, string][] = [
      ["chat.send", () => c.chat.send("ses_a", "hi"), "M3"],
      ["sessions.create", () => c.sessions.create({ worldId: "w", mode: "one_on_one", characterIds: [] }), "M3"],
      ["sessions.export", () => c.sessions.export("ses_a"), "M3"],
      ["jobs.start", () => c.jobs.start({ characterId: "chr_a", kind: "song" }), "M4"],
      ["worlds.uploadCover", () => c.worlds.uploadCover("wld_a", new Blob() as File), "M4"],
      ["characters.addKnowledge", () => c.characters.addKnowledge("chr_a", { type: "text", title: "t", text: "x" }), "M5"],
    ];
    for (const [name, call, m] of notYet) {
      const e = (await call().catch((x: unknown) => x)) as HorizonError;
      expect(e, name).toBeInstanceOf(HorizonError);
      expect([e.code, e.retryable, e.details?.availableIn], name).toEqual(["validation", false, m]);
    }
    expect(calls).toEqual([]);
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
});
