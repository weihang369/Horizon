import { existsSync } from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { makeTestBackendDirs, removeDirs, SEED, serveArgs, testBackendEnv } from "./env.ts";
import type { TestBackendDirs } from "./env.ts";

let dirs: TestBackendDirs | null = null;
afterEach(() => {
  if (dirs) removeDirs(dirs);
  dirs = null;
});

describe("test-mode backend recipe (http-client-parity D8)", () => {
  it("roots the backend in a fresh temp dir with no .env, and reads the repo seed", () => {
    dirs = makeTestBackendDirs("horizon-env-test-");
    const env = testBackendEnv(dirs, {});
    expect(env.HORIZON_ROOT).toBe(dirs.root);
    expect(existsSync(path.join(dirs.root, ".env"))).toBe(false);
    expect(env.HORIZON_SEED_DIR).toBe(SEED);
    expect(existsSync(path.join(SEED, "manifest.json"))).toBe(true);
    expect(env.HORIZON_DATA_DIR).toBe(path.join(dirs.root, "data"));
    expect(env).toMatchObject({ HORIZON_TEST: "1", HORIZON_AI_PROFILE: "scripted" });
  });

  it("drops everything Horizon would read from the caller's environment, and keeps the rest", () => {
    dirs = makeTestBackendDirs("horizon-env-test-");
    const env = testBackendEnv(dirs, {
      PATH: "/bin", HORIZON_AI_TURN: "naive", horizon_data_dir: "/real/data", OPENROUTER_API_KEY: "sk-or-test-not-real",
    });
    expect(env.PATH).toBe("/bin");
    expect(env.HORIZON_AI_TURN).toBeUndefined();
    expect(env.horizon_data_dir).toBeUndefined();
    expect(env.OPENROUTER_API_KEY).toBeUndefined();
  });

  it("serves on the given loopback port through uv", () => {
    expect(serveArgs(8786)).toEqual(expect.arrayContaining(["horizon", "serve", "--port", "8786"]));
  });
});
