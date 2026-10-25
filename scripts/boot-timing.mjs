#!/usr/bin/env node
// Fresh-clone boot timing (local-backend "Fresh clone within five minutes", NFR-10; http-client-parity D19).
// Clones the current commit into a temp dir, runs `npm run setup`, starts `npm run dev`, and waits until demo mode
// answers: the app at http://localhost:5173/ and the two seed worlds through its /api proxy. Prints setup, boot and
// total seconds (and appends them to $GITHUB_STEP_SUMMARY when set), stops everything, and fails over the budget.
// The same code is the Windows acceptance measurement and the CI (Linux) step.
//
//   node scripts/boot-timing.mjs [--cold] [--keep] [--budget=300]
//   --cold   empty npm, uv and Python-install caches, so every package and the Python runtime are downloaded
//   --keep   keep the clone (and its caches) for inspection
//
// No dependencies, no key: the clone has no .env, and inherited HORIZON_* / OPENROUTER_API_KEY are dropped.
// Docling (setup step 2) is never run. Ports 8000 and 5173 must be free (stop `npm run dev` first).
import { execFileSync, spawn, spawnSync } from "node:child_process";
import { appendFileSync, mkdtempSync, rmSync } from "node:fs";
import { createConnection } from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const cold = args.includes("--cold");
const keep = args.includes("--keep");
const budgetS = Number(args.find((a) => a.startsWith("--budget="))?.split("=")[1] ?? 300);
const APP = "http://localhost:5173";
const win = process.platform === "win32";

const log = (msg) => console.log(`[boot-timing] ${msg}`);
const seconds = (ms) => Math.round(ms / 100) / 10;

function portBusy(port) {
  return new Promise((resolve) => {
    const s = createConnection({ port, host: "localhost" });
    s.once("connect", () => { s.destroy(); resolve(true); });
    s.once("error", () => resolve(false));
  });
}

/** `npm run <script>`; on Windows through the shell as one string (npm is npm.cmd; no unescaped arg list). */
function npm(script, opts) {
  return win ? [`npm run ${script}`, [], { ...opts, shell: true }] : ["npm", ["run", script], opts];
}

function killTree(child) {
  if (!child || child.pid === undefined || child.exitCode !== null) return;
  if (win) spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  else {
    try { process.kill(-child.pid, "SIGTERM"); } catch { child.kill("SIGTERM"); }
  }
}

/** Demo mode answers: the app shell, and two seed worlds through the app's /api proxy. */
async function demoModeUp() {
  try {
    const page = await fetch(`${APP}/`);
    if (!page.ok) return false;
    const r = await fetch(`${APP}/api/v1/worlds`);
    if (!r.ok) return false;
    const worlds = await r.json();
    return Array.isArray(worlds) && ["wld_seedMeridian", "wld_seedSunnyHollow"].every((id) => worlds.some((w) => w.id === id));
  } catch {
    return false;
  }
}

function report(rows, ok) {
  const lines = [
    `### Fresh-clone boot ${ok ? "✅" : "❌"} (${cold ? "cold caches" : "warm caches"}, budget ${budgetS} s)`,
    "",
    "| Step | Seconds |",
    "|---|---|",
    ...rows.map(([k, v]) => `| ${k} | ${v} |`),
    "",
  ];
  console.log(lines.join("\n"));
  if (process.env.GITHUB_STEP_SUMMARY) appendFileSync(process.env.GITHUB_STEP_SUMMARY, `${lines.join("\n")}\n`);
}

for (const port of [8000, 5173]) {
  if (await portBusy(port)) {
    console.error(`[boot-timing] port ${port} is in use: stop \`npm run dev\` (or whatever holds it) and run again.`);
    process.exit(2);
  }
}

const sha = execFileSync("git", ["rev-parse", "HEAD"], { cwd: REPO, encoding: "utf8" }).trim();
const work = mkdtempSync(path.join(tmpdir(), "horizon-boot-"));
const clone = path.join(work, "Horizon");
// Cold runs replace these; Windows env names are case-insensitive, so every case variant is dropped first.
const COLD_KEYS = new Set(["NPM_CONFIG_CACHE", "UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "UV_PYTHON_PREFERENCE"]);
const env = {};
for (const [k, v] of Object.entries(process.env)) {
  const u = k.toUpperCase();
  if (u.startsWith("HORIZON_") || u === "OPENROUTER_API_KEY" || (cold && COLD_KEYS.has(u))) continue;
  env[k] = v;
}
if (cold) {
  Object.assign(env, {
    npm_config_cache: path.join(work, "npm-cache"),
    UV_CACHE_DIR: path.join(work, "uv-cache"),
    UV_PYTHON_INSTALL_DIR: path.join(work, "uv-python"),
    UV_PYTHON_PREFERENCE: "only-managed",   // ignore any Python already on the machine: download it, as a fresh machine would
  });
}

let dev = null;
let ok = false;
const rows = [];
const t0 = Date.now();
try {
  log(`cloning ${sha.slice(0, 10)} into ${clone}${cold ? " (cold caches)" : ""}`);
  execFileSync("git", ["clone", "--quiet", "--no-local", REPO, clone], { stdio: "inherit" });
  execFileSync("git", ["checkout", "--quiet", "--detach", sha], { cwd: clone, stdio: "inherit" });
  const tSetup = Date.now();
  log("npm run setup");
  const setup = spawnSync(...npm("setup", { cwd: clone, env, stdio: "inherit" }));
  if (setup.status !== 0) throw new Error(`npm run setup exited with ${setup.status}`);
  const setupMs = Date.now() - tSetup;
  rows.push(["clone", seconds(tSetup - t0)], ["npm run setup", seconds(setupMs)]);

  const tBoot = Date.now();
  log("npm run dev (waiting for demo mode)");
  dev = spawn(...npm("dev", { cwd: clone, env, stdio: ["ignore", "pipe", "pipe"], detached: !win }));
  let tail = "";
  const keepTail = (b) => { tail = (tail + b.toString()).slice(-4000); };
  dev.stdout.on("data", keepTail);
  dev.stderr.on("data", keepTail);
  const deadline = t0 + budgetS * 1000;
  while (Date.now() < deadline && dev.exitCode === null && !(await demoModeUp())) await new Promise((r) => setTimeout(r, 500));
  ok = await demoModeUp();
  rows.push(["npm run dev → demo mode", ok ? seconds(Date.now() - tBoot) : "not reached"]);
  rows.push(["total (clone → demo mode)", seconds(Date.now() - t0)]);
  if (!ok) console.error(`[boot-timing] demo mode not reached within ${budgetS} s. Last dev output:\n${tail}`);
} catch (e) {
  rows.push(["error", String(e instanceof Error ? e.message : e)]);
} finally {
  killTree(dev);
  ok = ok && Date.now() - t0 <= budgetS * 1000;
  report(rows, ok);
  if (!keep) {
    await new Promise((r) => setTimeout(r, 1000));   // Windows releases file handles after the tree is gone
    try { rmSync(work, { recursive: true, force: true, maxRetries: 10, retryDelay: 500 }); } catch (e) { log(`could not remove ${work}: ${e}`); }
  } else log(`kept ${work}`);
}
process.exit(ok ? 0 : 1);
