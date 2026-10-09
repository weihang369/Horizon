// One recipe for every test-mode backend a frontend test run starts (`npm run test:http`'s global setup and the E2E
// launcher), so neither ever touches the developer's own setup (http-client-parity D8, e2e-suite spec):
// - `HORIZON_ROOT` is a fresh temp dir with no `.env`, so the repo-root `.env` (AI overrides, data dir, key) is never read;
// - inherited `HORIZON_*` and `OPENROUTER_API_KEY` are dropped, because the environment outranks `.env`;
// - the seed comes from the repo, the data lives in the temp dir, and the AI profile is `scripted`.
// Plain erasable TypeScript: Node runs it directly (the E2E launcher), and vitest imports it. Owner: SWE.
import { spawnSync } from "node:child_process";
import type { ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
export const REPO = path.resolve(here, "../../..");
export const BACKEND = path.join(REPO, "backend");
export const SEED = path.join(REPO, "seed");

export interface TestBackendDirs {
  /** `HORIZON_ROOT`: holds no `.env`. */
  root: string;
  /** `HORIZON_DATA_DIR`: created by the backend on startup. */
  dataDir: string;
}

export function makeTestBackendDirs(prefix: string): TestBackendDirs {
  const root = mkdtempSync(path.join(tmpdir(), prefix));
  return { root, dataDir: path.join(root, "data") };
}

/** The environment for a test-mode backend: the caller's, minus anything Horizon reads, plus the test recipe. */
export function testBackendEnv(dirs: TestBackendDirs, base: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {};
  for (const [k, v] of Object.entries(base)) {
    const upper = k.toUpperCase();
    if (upper.startsWith("HORIZON_") || upper === "OPENROUTER_API_KEY") continue;
    env[k] = v;
  }
  return {
    ...env,
    HORIZON_ROOT: dirs.root,
    HORIZON_SEED_DIR: SEED,
    HORIZON_DATA_DIR: dirs.dataDir,
    HORIZON_TEST: "1",
    HORIZON_AI_PROFILE: "scripted",
    HORIZON_LOG_LEVEL: "WARNING",
  };
}

/** `uv run … horizon serve --port N` (loopback only, as the backend always is). */
export function serveArgs(port: number): string[] {
  return ["run", "--project", BACKEND, "horizon", "serve", "--port", String(port)];
}

/** Stop a backend and everything it started (uv → python → uvicorn): `taskkill /T` on Windows, the process group elsewhere. */
export function killTree(child: ChildProcess): void {
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

/** Remove the temp dir; Windows keeps SQLite/WAL handles until the process is fully gone, hence the retries. */
export function removeDirs(dirs: TestBackendDirs): void {
  rmSync(dirs.root, { recursive: true, force: true, maxRetries: 10, retryDelay: 300 });
}
