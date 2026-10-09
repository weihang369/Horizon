// Playwright E2E suite (docs/qa/r1-test-report.md): the acceptance suite for BOTH clients (http-client-parity D7,
// e2e-suite spec). The same specs run against the MockClient and against a test-mode backend through the HttpClient;
// they drive user-visible behaviour only, and client-specific steps live in e2e/fixtures.ts.
//   npm run e2e        all projects (mock-desktop, mock-min, http-desktop): the M6 acceptance
//   npm run e2e:mock   the MockClient projects        npm run e2e:http   the HttpClient project
//   npm run e2e:prod   the MockClient projects against the production build (vite preview of dist/, what Vercel serves)
// A web server starts only when a selected project needs it.
import { defineConfig, devices } from "@playwright/test";
import type { ClientKind } from "./e2e/servers/ports";
import { BACKEND_PORT, HTTP_WEB_PORT, MOCK_WEB_PORT } from "./e2e/servers/ports";

// Edge is installed on the dev machines, so no browser download is needed. Set PW_CHANNEL="" to use the bundled
// Chromium instead (CI does; locally it needs `npx playwright install chromium`).
const channel = process.env.PW_CHANNEL ?? "msedge";
// A deployed site with E2E_BASE_URL=https://… (no local server) is a MockClient target: run it with --project=mock-*.
const remote = process.env.E2E_BASE_URL;
const prod = process.env.npm_lifecycle_event === "e2e:prod";

const PROJECTS = ["mock-desktop", "mock-min", "http-desktop"] as const;

/** The projects named on the command line (`--project x`, `--project=x`, wildcards allowed); all of them by default. */
function selectedProjects(argv: string[]): Set<string> {
  const patterns: string[] = [];
  argv.forEach((a, i) => {
    if (a === "--project" && argv[i + 1]) patterns.push(argv[i + 1]);
    else if (a.startsWith("--project=")) patterns.push(a.slice("--project=".length));
  });
  if (!patterns.length) return new Set(PROJECTS);
  const res = patterns.map((p) => new RegExp(`^${p.replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*")}$`, "i"));
  return new Set(PROJECTS.filter((name) => res.some((re) => re.test(name))));
}
const selected = selectedProjects(process.argv);
const needsMock = !remote && (selected.has("mock-desktop") || selected.has("mock-min"));
const needsHttp = selected.has("http-desktop");

const mockBase = remote ?? `http://localhost:${MOCK_WEB_PORT}`;
const httpBase = `http://localhost:${HTTP_WEB_PORT}`;

export default defineConfig<{ client: ClientKind }>({
  testDir: "./e2e",
  outputDir: "./test-results",
  // The owner's machine is CPU-bound: one worker locally, two on CI. The HTTP project is serial (one shared backend).
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : 1,
  timeout: 45_000,
  expect: { timeout: 8_000 },
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  use: {
    ...devices["Desktop Chrome"],
    ...(channel ? { channel } : {}),
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "mock-desktop",
      use: { client: "mock", baseURL: mockBase, viewport: { width: 1440, height: 900 } },
    },
    {
      // The 1280×720 minimum (APP-06), with reduced motion. Only the layout-critical specs run here; layout doesn't
      // depend on the client, so this project is MockClient-only.
      name: "mock-min",
      grep: /@layout/,
      use: { client: "mock", baseURL: mockBase, viewport: { width: 1280, height: 720 }, reducedMotion: "reduce" },
    },
    {
      // The HttpClient against a test-mode backend (scripted AI, temp data, factory reset before every test).
      name: "http-desktop",
      workers: 1,
      use: { client: "http", baseURL: httpBase, viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: [
    ...(needsMock
      ? [{
        command: prod ? `npx vite preview --port ${MOCK_WEB_PORT} --strictPort` : `npx vite --port ${MOCK_WEB_PORT} --strictPort`,
        url: mockBase,
        // Never reuse a dev server for a production run (and vice versa).
        reuseExistingServer: !process.env.CI && !prod,
        timeout: 60_000,
      }]
      : []),
    ...(needsHttp
      ? [
        {
          // The test-mode backend (e2e/servers/backend.ts). Never reused: a server already on this port could be a
          // developer's backend with real data, so an occupied port fails the run instead.
          command: `node e2e/servers/backend.ts ${BACKEND_PORT}`,
          url: `http://127.0.0.1:${BACKEND_PORT}/api/v1/health`,
          reuseExistingServer: false,
          timeout: 180_000,
          // Linux/macOS: SIGTERM first so the launcher stops the backend and removes its temp dir; SIGKILL after 15 s.
          // Windows ignores this and force-kills the tree (the launcher sweeps stale dirs on its next start).
          gracefulShutdown: { signal: "SIGTERM" as const, timeout: 15_000 },
          stdout: "ignore" as const,
          stderr: "pipe" as const,
        },
        {
          command: `npx vite --mode http --port ${HTTP_WEB_PORT} --strictPort`,
          url: httpBase,
          env: { HORIZON_API_TARGET: `http://127.0.0.1:${BACKEND_PORT}` },
          reuseExistingServer: false,
          timeout: 60_000,
        },
      ]
      : []),
  ],
});
