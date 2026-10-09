// Shared fixtures and helpers for the E2E suite, which runs on BOTH clients (http-client-parity D7–D12).
// - Every test fails on console errors/warnings and uncaught page errors (allow-list below). On HTTP, a 4xx resource
//   error is accepted only when the test declared that status with `expectHttpError` (D12).
// - Helpers only use what a user can see or do: URLs, roles, labels, text, keys. Steps that differ between clients
//   (`setKey`, `setScenario`, `GEN_TIMEOUT`) live here, so specs never branch on the client.
// - On HTTP, every test starts from a factory reset of the test backend (D9).
import { expect, test as base, type Locator, type Page } from "@playwright/test";
import { BACKEND_API, type ClientKind } from "./servers/ports";

/** Known, accepted console noise. Keep this list short and explain every entry. */
const CONSOLE_ALLOW: RegExp[] = [
  // Chromium logs this when the audio engine is created before the first user gesture (autoplay policy).
  /The AudioContext was not allowed to start/,
];
/** Chromium/Edge's line for a non-2xx response (verified in apply, design.md "Apply notes"). */
const RESOURCE_ERROR = /^Failed to load resource: the server responded with a status of (\d{3})\b/;

const clientOf = new WeakMap<Page, ClientKind>();
const expectedStatuses = new WeakMap<Page, Set<number>>();

/** The client this page's project runs against. */
export function clientFor(page: Page): ClientKind {
  return clientOf.get(page) ?? "mock";
}

/**
 * Declares a 4xx the test expects from the backend (a refusal it asserts on), so the browser's resource-error line for
 * it does not fail the test. A no-op on the MockClient, which makes no requests. 5xx can never be declared.
 */
export function expectHttpError(page: Page, status: number): void {
  if (status < 400 || status > 499) throw new Error(`only 4xx responses can be expected (got ${status})`);
  const set = expectedStatuses.get(page) ?? new Set<number>();
  set.add(status);
  expectedStatuses.set(page, set);
}

async function backend(path: string, body: unknown): Promise<void> {
  const r = await fetch(`${BACKEND_API}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`test backend ${path}: ${r.status} ${await r.text()}`);
}

type Options = {
  /** The project's client (playwright.config.ts). */
  client: ClientKind;
};
type Fixtures = {
  /** Collected console problems; asserted empty after each test. */
  consoleProblems: string[];
  /** Records the page's client and, on HTTP, factory-resets the test backend before the test (D9). */
  clientSetup: void;
};

export const test = base.extend<Options & Fixtures>({
  client: ["mock", { option: true }],
  clientSetup: [
    async ({ page, client }, use) => {
      clientOf.set(page, client);
      if (client === "http") await backend("/admin/factory-reset", { confirm: "DELETE EVERYTHING" });
      await use();
    },
    { auto: true },
  ],
  consoleProblems: [
    async ({ page }, use, testInfo) => {
      const problems: string[] = [];
      page.on("console", (msg) => {
        if (msg.type() !== "error" && msg.type() !== "warning") return;
        const text = msg.text();
        if (CONSOLE_ALLOW.some((re) => re.test(text))) return;
        const status = Number(RESOURCE_ERROR.exec(text)?.[1]);
        if (status >= 400 && status <= 499 && expectedStatuses.get(page)?.has(status) && msg.location().url.includes("/api/")) return;
        problems.push(`[console.${msg.type()}] ${text}${msg.location().url ? ` (${msg.location().url})` : ""}`);
      });
      page.on("pageerror", (err) => problems.push(`[pageerror] ${err.message}`));
      await use(problems);
      if (problems.length) await testInfo.attach("console-problems", { body: problems.join("\n"), contentType: "text/plain" });
      expect(problems, "console must stay clean (errors, warnings, page errors)").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };

/**
 * Marks onboarding as seen, the way a returning visitor's browser has it. Prefs live in localStorage under
 * "horizon.prefs.v1" as a flat, partial object (src/stores/prefs.ts); missing fields fall back to defaults.
 */
export async function returningVisitor(page: Page): Promise<void> {
  await page.addInitScript(() => {
    if (!localStorage.getItem("horizon.prefs.v1")) localStorage.setItem("horizon.prefs.v1", JSON.stringify({ seenOnboarding: true }));
  });
}

/**
 * Opens a hash route as a returning visitor. `speed` uses the documented `?speed=` deep link so mock generation
 * and streaming finish quickly; it is ignored by a real backend.
 */
export async function open(page: Page, hash: string, opts: { speed?: 1 | 2 | 4 } = {}): Promise<void> {
  await returningVisitor(page);
  const search = opts.speed ? `?speed=${opts.speed}` : "";
  await page.goto(`/${search}#${hash.replace(/^#/, "")}`);
}

/** "0:16 of 0:16": the replay playhead is at the end. */
const AT_END = /^(\d+:\d\d) of \1$/;

/**
 * Jumps a replay to its last event via the Seek slider (keyboard End), and waits until the log has caught up.
 * One press must be enough (QA-01 regression guard).
 */
export async function seekToEnd(page: Page): Promise<void> {
  const seek = page.getByRole("slider", { name: "Seek" });
  await expect(seek).toHaveAttribute("aria-valuetext", /of \d+:\d\d$/);
  await seek.focus();
  await page.keyboard.press("End");
  await expect(seek).toHaveAttribute("aria-valuetext", AT_END);
  await expect(page.getByRole("log").getByRole("listitem").nth(2)).toBeVisible();
}

/** Waits for the title screen, then presses a key to start (keys pressed before it mounts are lost). */
export async function pressStartOnTitle(page: Page): Promise<void> {
  await expect(page.getByRole("button", { name: "Press any key to start" })).toBeVisible();
  await page.keyboard.press("Enter");
}

/** The fake key the E2E suite saves (never a real one): accepted by the MockClient and by the test backend's fake provider. */
export const E2E_KEY = "sk-or-test-e2e-0001";

/**
 * Sets an OpenRouter key the way a user does on both clients: Settings → Connection → paste → "Save key", then back to
 * the page the test was on (an in-app hash change, so nothing reloads). Replaces the old mock-only switcher step (D10).
 */
export async function setKey(page: Page): Promise<void> {
  await page.evaluate(() => { location.hash = "#/settings"; });
  await page.getByLabel(/^(Key|Replace key)$/).fill(E2E_KEY);
  await page.getByRole("button", { name: "Save key" }).click();
  await expect(page.getByText("KEY SET")).toBeVisible();
  await page.goBack();
}

/** Scenarios the E2E specs apply (a subset of the mock switcher's, all mirrored by the test backend). */
export type E2EScenario = "daily_cap" | "character_exhausted" | "rush_hour";
const SCENARIO_LABEL: Record<E2EScenario, RegExp> = {
  daily_cap: /Daily cap reached/, character_exhausted: /Character exhausted/, rush_hour: /Rush hour/,
};

/**
 * Applies a scenario: through the mock state switcher (Ctrl+Shift+D) on the MockClient, through the test backend's
 * `/_test/scenario` on HTTP. Either way the open screen picks it up from the global stream (D10).
 */
export async function setScenario(page: Page, id: E2EScenario): Promise<void> {
  if (clientFor(page) === "http") {
    await backend("/_test/scenario", { id });
    return;
  }
  await page.keyboard.press("Control+Shift+D");
  const panel = page.getByRole("complementary", { name: /MOCK STATE/ });
  await expect(panel).toBeVisible();
  await panel.getByRole("button", { name: SCENARIO_LABEL[id] }).click();
  await panel.getByRole("button", { name: "Close", exact: true }).click();
  await expect(panel).toBeHidden();
}

/**
 * How long to wait for a generation job to land. The mock runs at `?speed=4`; the backend paces jobs in real time (a
 * portrait takes 20 s, seed/runtime.json), so HTTP waits longer (D11).
 */
export function genTimeout(page: Page): number {
  return clientFor(page) === "http" ? 60_000 : 8_000;
}

/** The log entry (listitem) whose text contains `text`. */
export function logEntry(page: Page, text: string | RegExp): Locator {
  return page.getByRole("log").getByRole("listitem").filter({ hasText: text });
}
