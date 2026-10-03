// Shared fixtures and helpers for the E2E suite.
// - Every test fails on console errors/warnings and uncaught page errors (allow-list below).
// - Helpers only use what a user can see or do: URLs, roles, labels, text, keys.
import { expect, test as base, type Locator, type Page } from "@playwright/test";

/** Known, accepted console noise. Keep this list short and explain every entry. */
const CONSOLE_ALLOW: RegExp[] = [
  // Chromium logs this when the audio engine is created before the first user gesture (autoplay policy).
  /The AudioContext was not allowed to start/,
];

type Fixtures = {
  /** Collected console problems; asserted empty after each test. */
  consoleProblems: string[];
};

export const test = base.extend<Fixtures>({
  consoleProblems: [
    async ({ page }, use, testInfo) => {
      const problems: string[] = [];
      page.on("console", (msg) => {
        if (msg.type() !== "error" && msg.type() !== "warning") return;
        const text = msg.text();
        if (CONSOLE_ALLOW.some((re) => re.test(text))) return;
        problems.push(`[console.${msg.type()}] ${text}`);
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
 * The first keyboard seek after a replay opens snaps back to 0:00 without delivering anything (QA-01), so this presses
 * End again until the playhead is at the end AND the log shows delivered messages.
 */
export async function seekToEnd(page: Page): Promise<void> {
  const seek = page.getByRole("slider", { name: "Seek" });
  await expect(seek).toHaveAttribute("aria-valuetext", /of \d+:\d\d$/);
  await expect(async () => {
    await seek.focus();
    await page.keyboard.press("End");
    await expect(seek).toHaveAttribute("aria-valuetext", AT_END, { timeout: 1_000 });
    await expect(page.getByRole("log").getByRole("listitem").nth(2)).toBeVisible({ timeout: 1_000 });
  }).toPass({ timeout: 10_000 });
  await expect(seek).toHaveAttribute("aria-valuetext", AT_END);
}

/** Waits for the title screen, then presses a key to start (keys pressed before it mounts are lost). */
export async function pressStartOnTitle(page: Page): Promise<void> {
  await expect(page.getByRole("button", { name: "Press any key to start" })).toBeVisible();
  await page.keyboard.press("Enter");
}

/** Opens the mock state switcher (Ctrl+Shift+D) and sets the mock OpenRouter key. */
export async function setMockKey(page: Page): Promise<void> {
  await page.keyboard.press("Control+Shift+D");
  const panel = page.getByRole("complementary", { name: /MOCK STATE/ });
  await expect(panel).toBeVisible();
  await panel.getByRole("button", { name: "Set mock key" }).click();
  await expect(page.getByText(/Mock key set/)).toBeVisible();
  await panel.getByRole("button", { name: "Close", exact: true }).click();
  await expect(panel).toBeHidden();
}

/** The log entry (listitem) whose text contains `text`. */
export function logEntry(page: Page, text: string | RegExp): Locator {
  return page.getByRole("log").getByRole("listitem").filter({ hasText: text });
}
