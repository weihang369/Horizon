// The E2E HTTP project's backend (http-client-parity D8, D13; e2e-suite spec "The backend under test is isolated").
// Run by Playwright's webServer as `node e2e/servers/backend.ts [port]` (Node strips the types). It starts a test-mode
// backend from the shared recipe (scripts/test-backend/env.ts: temp HORIZON_ROOT with no .env, repo seed, temp data dir,
// scripted AI, no inherited HORIZON_* or key) on 127.0.0.1:<port>, default 8786, and owns its lifecycle:
// - Ctrl-C / SIGTERM / its own exit: kill the backend's process tree (uv → python → uvicorn), then remove the temp dir;
// - Playwright on Windows kills this launcher forcefully, so no handler runs. Each temp dir therefore records its
//   launcher's PID, and every start sweeps the dirs of launchers that are no longer alive.
// - On Linux/macOS the backend stays in this launcher's process group (not detached): Playwright SIGTERMs, then
//   SIGKILLs, that group, and waits for the stderr pipe the backend inherits. A detached backend would survive the
//   kill, hold the pipe open and hang Playwright's teardown (CI run 3 hit the 45 min limit that way).
// Owner: SWE.
import { spawn } from "node:child_process";
import { readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { BACKEND, killTree, makeTestBackendDirs, removeDirs, serveArgs, testBackendEnv } from "../../scripts/test-backend/env.ts";

const PREFIX = "horizon-e2e-";
const port = Number(process.argv[2] ?? process.env.E2E_BACKEND_PORT ?? 8786);

function alive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (e) {
    return (e as NodeJS.ErrnoException).code === "EPERM";
  }
}

/** Remove the temp dirs of earlier launchers that died without cleaning up (a forced kill, a crash). */
function sweepStale(): void {
  for (const name of readdirSync(tmpdir())) {
    if (!name.startsWith(PREFIX)) continue;
    const dir = path.join(tmpdir(), name);
    let owner = NaN;
    try {
      owner = Number(readFileSync(path.join(dir, "launcher.pid"), "utf8"));
    } catch {
      /* no pid file: a launcher that died before writing it, or a half-removed dir */
    }
    if (Number.isFinite(owner) && alive(owner)) continue;
    rmSync(dir, { recursive: true, force: true, maxRetries: 3, retryDelay: 200 });
  }
}

sweepStale();
const dirs = makeTestBackendDirs(PREFIX);
writeFileSync(path.join(dirs.root, "launcher.pid"), String(process.pid));
const child = spawn("uv", serveArgs(port), {
  cwd: BACKEND,
  env: testBackendEnv(dirs),
  stdio: ["ignore", "inherit", "inherit"],
});

let stopping = false;
function stop(code: number): void {
  if (stopping) return;
  stopping = true;
  killTree(child);
  // Give Windows a moment to release the SQLite/WAL handles before the directory goes.
  setTimeout(() => {
    try {
      removeDirs(dirs);
    } finally {
      process.exit(code);
    }
  }, 500);
}

child.on("exit", (code) => {
  if (stopping) return;
  console.error(`[e2e backend] exited early (code ${code ?? "signal"})`);
  stop(code ?? 1);
});
for (const sig of ["SIGINT", "SIGTERM", "SIGHUP", "SIGBREAK"] as const) process.on(sig, () => stop(0));
process.on("exit", () => killTree(child));   // last resort: never leave the backend running
