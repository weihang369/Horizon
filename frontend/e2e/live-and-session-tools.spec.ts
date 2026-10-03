// "Going live" on a replay (CHAT-*, F3) and the session tools: Backlog (O10), Markdown export, Readable mode.
import { expect, logEntry, open, seekToEnd, setMockKey, test } from "./fixtures";

const HEADACHE = "/w/wld_seedMeridian/s/ses_seedAmaraHeadache?replay=1";

test("live mock: set a key, “Continue live” on a replay, send a message, a streamed reply arrives", async ({ page }) => {
  await open(page, HEADACHE);
  await expect(page.getByRole("button", { name: /Continue live.*needs API key/ })).toBeVisible();
  await setMockKey(page);
  await page.getByRole("button", { name: /^Continue live/ }).click();

  await expect(page.getByRole("heading", { name: "Three-day headache · live", level: 1 })).toBeVisible();
  await expect(page).not.toHaveURL(/replay=1/);
  const input = page.getByRole("textbox", { name: "Talk to Amara" });
  await input.fill("Should I see a doctor today?");
  await page.keyboard.press("Enter");

  await expect(logEntry(page, "Should I see a doctor today?")).toBeVisible();
  // While the reply streams, Send turns into Stop; it turns back when the reply is done.
  await expect(page.getByRole("button", { name: "Stop the reply (Ctrl+.)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Stop the reply (Ctrl+.)" })).toBeHidden({ timeout: 20_000 });
  // The newest reply is the one that offers "Regenerate reply".
  const reply = page.getByRole("log").getByRole("listitem").filter({ has: page.getByRole("button", { name: "Regenerate reply" }) });
  await expect(reply).toHaveCount(1);
  await expect(reply).toContainText("Amara");
  await expect(reply.getByRole("paragraph").first()).toHaveText(/\w+(\s+\w+){5,}/);
  await expect(input).toHaveValue("");
});

test("Backlog: L opens the full log, it exports Markdown, Esc closes it @layout", async ({ page }) => {
  await open(page, HEADACHE);
  await seekToEnd(page);
  await page.keyboard.press("l");
  const backlog = page.getByRole("dialog", { name: "Backlog" });
  await expect(backlog).toBeVisible();
  await expect(backlog.getByText("Three-day headache")).toBeVisible();
  await expect(backlog).toContainText("I've had a headache for three days");
  await expect(backlog).toContainText("this is the honest caveat");

  await backlog.getByRole("searchbox", { name: "Search this conversation" }).fill("caffeine");
  await expect(backlog.locator("mark").first()).toHaveText(/caffeine/i);

  const [download] = await Promise.all([page.waitForEvent("download"), backlog.getByRole("button", { name: "Export .md" }).click()]);
  expect(download.suggestedFilename()).toBe("three-day-headache.md");

  await page.keyboard.press("Escape");
  await expect(backlog).toBeHidden();
});

test("Backlog: pressing L again closes it, as its “Close backlog (L)” button promises", async ({ page }) => {
  // QA-02: the search box takes focus on open, so the second L is typed into the search instead of closing.
  test.fail();
  await open(page, HEADACHE);
  await seekToEnd(page);
  await page.keyboard.press("l");
  const backlog = page.getByRole("dialog", { name: "Backlog" });
  await expect(backlog.getByRole("button", { name: "Close backlog (L)" })).toBeVisible();
  await page.keyboard.press("l");
  await expect(backlog).toBeHidden({ timeout: 3_000 });
});

test("Readable mode toggles on and off from the session header", async ({ page }) => {
  await open(page, HEADACHE);
  await seekToEnd(page);
  const readable = page.getByRole("button", { name: "Readable", exact: true });
  await expect(readable).toHaveAttribute("aria-pressed", "false");
  await readable.click();
  await expect(readable).toHaveAttribute("aria-pressed", "true");
  await expect(logEntry(page, "honest caveat")).toBeVisible();
  await readable.click();
  await expect(readable).toHaveAttribute("aria-pressed", "false");
});
