// A late fetch answer never overwrites newer data (found over HTTP: a job GET started before job.done landed after it
// and left the wizard on "Developing…").
import { describe, expect, it } from "vitest";
import { entities, invalidate, loadResource, putResource } from "./entities";

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

const res = (key: string) => entities.getState().res[key];
const flush = () => new Promise((r) => setTimeout(r, 0));

describe("loadResource", () => {
  it("drops an answer that started before a write", async () => {
    const answer = deferred<string>();
    let calls = 0;
    const p = loadResource("t:put", () => (calls++, answer.promise));
    putResource("t:put", "done");                // job.done lands while the GET is on the wire
    answer.resolve("running");                   // the stale answer
    await expect(p).resolves.toBe("done");
    expect(res("t:put")?.data).toBe("done");
    expect(calls).toBe(1);
  });

  it("does not reuse a fetch that started before an invalidation, and the older answer loses", async () => {
    const answers = [deferred<string>(), deferred<string>()];
    let calls = 0;
    const fetcher = () => answers[calls++].promise;
    putResource("t:inv", "v0");
    const old = loadResource("t:inv", fetcher, { force: true });
    invalidate((k) => k === "t:inv");
    const fresh = loadResource("t:inv", fetcher, { force: true });
    expect(calls).toBe(2);
    answers[1].resolve("v2");
    await fresh;
    answers[0].resolve("v1");                    // the older answer arrives last
    await old;
    await flush();
    expect(res("t:inv")?.data).toBe("v2");
    expect(calls).toBe(2);
  });

  it("refetches a first load that was invalidated mid-flight (no hook reloads a loading key)", async () => {
    const answers = [deferred<string>(), deferred<string>()];
    let calls = 0;
    const p = loadResource("t:first", () => answers[calls++].promise);
    expect(res("t:first")?.status).toBe("loading");
    invalidate((k) => k === "t:first");
    answers[0].resolve("before");
    await flush();
    expect(calls).toBe(2);
    answers[1].resolve("after");
    await expect(p).resolves.toBe("after");
    expect(res("t:first")).toMatchObject({ data: "after", status: "ready" });
  });

  it("still dedupes concurrent loads of the same version", async () => {
    const answer = deferred<string>();
    let calls = 0;
    const fetcher = () => (calls++, answer.promise);
    const a = loadResource("t:dedupe", fetcher);
    const b = loadResource("t:dedupe", fetcher, { force: true });
    answer.resolve("x");
    expect(await a).toBe("x");
    expect(await b).toBe("x");
    expect(calls).toBe(1);
  });
});
