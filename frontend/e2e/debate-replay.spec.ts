// Flow F1/F4: replaying the seeded four-day-week debate (MULTI-06/07/08, O23 replay transport, S11 verdict).
import { expect, open, seekToEnd, test } from "./fixtures";

const DEBATE = "/w/wld_seedMeridian/s/ses_seedDebate4Day?replay=1";

/** Seconds into the replay, read from the Seek slider's "m:ss of m:ss" text. */
async function position(page: import("@playwright/test").Page): Promise<number> {
  const text = (await page.getByRole("slider", { name: "Seek" }).getAttribute("aria-valuetext")) ?? "";
  const [m, s] = text.split(" of ")[0].split(":").map(Number);
  return m * 60 + s;
}

test("debate replay: Space plays and pauses, speed radios, ←/→ step turn by turn", async ({ page }) => {
  await open(page, DEBATE);
  await expect(page.getByRole("heading", { name: "This house would adopt a nationwide four-day work week.", level: 1 })).toBeVisible();
  const play = page.getByRole("button", { name: "Play replay (Space)" });
  await expect(play).toBeFocused();

  await page.keyboard.press("Space");
  const pause = page.getByRole("button", { name: "Pause replay (Space)" });
  await expect(pause).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Debate timeline" }).getByText("Opening (current)")).toBeVisible();
  await expect.poll(() => position(page), { message: "the playhead advances while playing" }).toBeGreaterThan(0);

  // Space pauses. A ceremony (VS splash / round banner) that is on screen takes the key press to skip itself
  // first (by design), so press again until the transport shows ▶.
  await expect(async () => {
    await page.keyboard.press("Space");
    await expect(play).toBeVisible({ timeout: 1_500 });
  }).toPass({ timeout: 10_000 });
  const paused = await position(page);
  await expect.poll(() => position(page), { message: "the playhead stays put while paused" }).toBe(paused);

  const speed = page.getByRole("radiogroup", { name: "Playback speed" });
  await speed.getByRole("radio", { name: "×4" }).click();
  await expect(speed.getByRole("radio", { name: "×4" })).toHaveAttribute("aria-checked", "true");
  await expect(speed.getByRole("radio", { name: "×1" })).toHaveAttribute("aria-checked", "false");

  // ←/→ step turn by turn (focus back on the transport, as after a mouse click elsewhere).
  // Pausing near 0:01 can leave the "Round 1" banner up; any key skips a ceremony first (D-55) and screen shortcuts
  // are muted under it, so the first → may only dismiss the banner. Once it is gone, every press must land (QA-01).
  await play.focus();
  await expect(async () => {
    await page.keyboard.press("ArrowRight");
    await expect.poll(() => position(page), { timeout: 1_500 }).toBeGreaterThan(paused);
  }).toPass({ timeout: 10_000 });
  const stepped = await position(page);
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => position(page)).toBeGreaterThan(stepped);
  await page.keyboard.press("ArrowLeft");
  await expect.poll(() => position(page)).toBe(stepped);
});

test("debate replay: “See the verdict” opens the verdict screen @layout", async ({ page }) => {
  await open(page, DEBATE);
  await seekToEnd(page);
  await expect(page.getByText("The arbiter has spoken")).toBeVisible();
  await page.getByRole("button", { name: "See the verdict ▸" }).click();

  await expect(page).toHaveURL(/#\/w\/wld_seedMeridian\/s\/ses_seedDebate4Day\/verdict$/);
  await expect(page.getByText("STRONGER CASE: PROPOSITION")).toBeVisible();
  await expect(page.getByRole("region", { name: "Rubric scores" })).toContainText("Evidence");
  await expect(page.getByText("Key disagreement")).toBeVisible();
  for (const name of ["Export Markdown", "Rematch", "Back to Hub", "Continue as group chat ▸"]) {
    await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
  }

  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Export Markdown" }).click()]);
  expect(download.suggestedFilename()).toMatch(/\.md$/);

  await page.getByRole("button", { name: "Back to Hub" }).click();
  await expect(page.getByRole("heading", { name: "MERIDIAN COUNCIL", level: 1 })).toBeVisible();
});

test("the first seek after opening a replay sticks (keyboard End on the Seek slider)", async ({ page }) => {
  // QA-01 (fixed): the first End used to snap back to 0:00 because the native `change` re-seeked to a stale value.
  await open(page, DEBATE);
  const seek = page.getByRole("slider", { name: "Seek" });
  await expect(seek).toHaveAttribute("aria-valuetext", /of 0:5\d$/);
  await page.keyboard.press("Tab");
  await expect(seek).toBeFocused();
  await page.keyboard.press("End");
  await expect(page.getByText("The arbiter has spoken")).toBeVisible({ timeout: 3_000 });
  await expect(seek).toHaveAttribute("aria-valuetext", "0:57 of 0:57");
});

test("a replay opens with a Watch call to action that starts playback", async ({ page }) => {
  await open(page, DEBATE);
  const watch = page.getByRole("button", { name: /^Watch/ });
  await expect(watch).toBeVisible();
  await watch.click();
  await expect(page.getByRole("button", { name: "Pause replay (Space)" })).toBeVisible();
  await expect(watch).toBeHidden();
});
