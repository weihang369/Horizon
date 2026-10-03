// Playwright E2E suite (docs/qa/r1-test-report.md). Tests drive user-visible behaviour only, so the same specs can
// run as an acceptance suite against the real API later. Run with `npm run e2e`.
import { defineConfig, devices } from "@playwright/test";

const PORT = 5186;
// Edge is installed on the dev machines, so no browser download is needed. Set PW_CHANNEL="" to use the bundled
// Chromium instead (needs `npx playwright install chromium`).
const channel = process.env.PW_CHANNEL ?? "msedge";
// Targets: the dev server (default); the production build via `npm run e2e:prod` (vite preview of dist/, what Vercel
// serves); or a deployed site with E2E_BASE_URL=https://… (no local server).
const remote = process.env.E2E_BASE_URL;
const prod = process.env.npm_lifecycle_event === "e2e:prod";

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",
  // The owner's machine is CPU-bound: one worker locally, two on CI.
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : 1,
  timeout: 45_000,
  expect: { timeout: 8_000 },
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: remote ?? `http://localhost:${PORT}`,
    ...devices["Desktop Chrome"],
    ...(channel ? { channel } : {}),
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "desktop-1440",
      use: { viewport: { width: 1440, height: 900 } },
    },
    {
      // The 1280×720 minimum (APP-06), with reduced motion. Only the layout-critical specs run here.
      name: "min-1280-reduced-motion",
      grep: /@layout/,
      use: { viewport: { width: 1280, height: 720 }, reducedMotion: "reduce" },
    },
  ],
  webServer: remote ? undefined : {
    command: prod ? `npx vite preview --port ${PORT} --strictPort` : `npx vite --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    // Never reuse a dev server for a production run (and vice versa).
    reuseExistingServer: !process.env.CI && !prod,
    timeout: 60_000,
  },
});
