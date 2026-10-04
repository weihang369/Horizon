// Starts a test-mode backend for the HTTP contract run (`npm run test:http`) and stops it afterwards. Owner: SWE.
// HORIZON_TEST=1 mounts /_test/*, validates every response against schema.json and loads the _mock overlays, so the
// portable suite sees the MockClient's dataset. Each run gets its own temporary data directory.
import { spawn, spawnSync } from "node:child_process";
import type { ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { TestProject } from "vitest/node";

declare module "vitest" {
  export interface ProvidedContext { horizonBaseUrl: string }
}

const here = path.dirname(fileURLToPath(import.meta.url));
const BACKEND = path.resolve(here, "../../../backend");

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

function killTree(child: ChildProcess): void {
  if (child.pid === undefined || child.exitCode !== null) return;
  if (process.platform === "win32") spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  else {
    try {
      process.kill(-child.pid, "SIGTERM");
    } catch {
      child.kill("SIGTERM");
    }
  }
}

export default async function setup(project: TestProject): Promise<() => Promise<void>> {
  const port = await freePort();
  const dataDir = mkdtempSync(path.join(tmpdir(), "horizon-http-"));
  const base = `http://127.0.0.1:${port}/api/v1`;
  const child = spawn("uv", ["run", "--project", BACKEND, "horizon", "serve", "--port", String(port)], {
    cwd: BACKEND,
    env: { ...process.env, HORIZON_TEST: "1", HORIZON_DATA_DIR: dataDir, HORIZON_LOG_LEVEL: "WARNING", HORIZON_AI_PROFILE: "scripted" },
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
    rmSync(dataDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  };
}
