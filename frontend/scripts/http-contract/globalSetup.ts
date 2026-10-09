// Starts a test-mode backend for the HTTP contract run (`npm run test:http`) and stops it afterwards. Owner: SWE.
// HORIZON_TEST=1 mounts /_test/*, validates every response against schema.json and loads the _mock overlays, so the
// portable suite sees the MockClient's dataset. The environment comes from the shared recipe (../test-backend/env.ts):
// a temp HORIZON_ROOT with no .env, the repo seed, a temp data dir and the scripted AI profile.
import { spawn } from "node:child_process";
import type { ChildProcess } from "node:child_process";
import { createServer } from "node:net";
import type { TestProject } from "vitest/node";
import { BACKEND, killTree, makeTestBackendDirs, removeDirs, serveArgs, testBackendEnv } from "../test-backend/env.ts";

declare module "vitest" {
  export interface ProvidedContext { horizonBaseUrl: string }
}

function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = createServer();
    srv.once("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const port = (srv.address() as { port: number }).port;
      srv.close(() => resolve(port));
    });
  });
}

async function waitHealthy(base: string, child: ChildProcess, ms = 120_000): Promise<void> {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (child.exitCode !== null) throw new Error(`backend exited early (code ${child.exitCode})`);
    try {
      const r = await fetch(`${base}/health`);
      if (r.ok && ((await r.json()) as { ok: boolean }).ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`backend not healthy at ${base} after ${ms} ms`);
}

export default async function setup(project: TestProject): Promise<() => Promise<void>> {
  const port = await freePort();
  const dirs = makeTestBackendDirs("horizon-http-");
  const base = `http://127.0.0.1:${port}/api/v1`;
  const child = spawn("uv", serveArgs(port), {
    cwd: BACKEND,
    env: testBackendEnv(dirs),
    stdio: ["ignore", "ignore", "inherit"],
    detached: process.platform !== "win32",
  });
  try {
    await waitHealthy(base, child);
  } catch (e) {
    killTree(child);
    throw e;
  }
  project.provide("horizonBaseUrl", base);
  return async () => {
    killTree(child);
    await new Promise((r) => setTimeout(r, 300));
    removeDirs(dirs);
  };
}
