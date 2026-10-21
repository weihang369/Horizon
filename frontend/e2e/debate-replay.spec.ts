// Flow F1/F4: replaying the seeded four-day-week debate (MULTI-06/07/08, O23 replay transport, S11 verdict).
import { expect, logEntry, open, seekToEnd, test } from "./fixtures";

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
  await expect(page.getByText("STRONGER CASE: OPPOSITION")).toBeVisible();
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
  await expect(seek).toHaveAttribute("aria-valuetext", /of 0:57$/);
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

test("Insight: the drawer's edge resizes it (drag, keys, double-click), the debate makes room, the width is kept; no pipeline chip is cut", async ({ page }) => {
  // U-30: the eight pipeline chips (STATE … KEEP) had equal shares of 400 px, so DECIDE / GATHER / SEARCH were cut.
  await open(page, DEBATE);
  await seekToEnd(page);
  const mei = logEntry(page, "Opposition's case rests on three things").first();
  await mei.hover();
  await mei.getByRole("button", { name: "Open Insight for this message" }).click();
  const insight = page.getByRole("complementary", { name: "Insight" });
  await expect(insight.getByRole("list", { name: "Turn pipeline" }).locator("li")).toHaveCount(8); // STATE … KEEP
  // U-35: each chip says what its step is and jumps to its panel
  const top = async (l: import("@playwright/test").Locator) => Math.round((await l.boundingBox())?.y ?? -1);
  const passages = insight.locator('[data-purpose="deep_check"]').first();
  const plan = insight.locator('[data-purpose="debate_plan"], [data-purpose="turn_plan"]').first();
  expect(await top(passages)).toBeGreaterThan(400);
  // U-36: Passages opens with the outcome; the set check said no, so no passage answers it alone
  await expect(passages.locator("[data-outcome]")).toHaveText(/^partly.*the reply gets the 2 usable passages\.$/);
  await insight.getByRole("button", { name: /^check: Jev judges each passage found/ }).click();
  await expect.poll(() => top(passages)).toBeLessThan(200);
  await insight.getByRole("button", { name: /^state: The situation, written as data for Jev/ }).click();
  await expect.poll(async () => { const y = await top(plan); return y >= 0 && y < 200; }).toBe(true);
  const edge = insight.getByRole("separator", { name: "Resize Insight" });
  await expect(edge).toHaveAttribute("aria-valuenow", "400");
  await expect.poll(async () => Math.round((await insight.boundingBox())?.width ?? 0)).toBe(400);

  const cut = () => insight.getByRole("list", { name: "Turn pipeline" }).locator("li").evaluateAll((lis) =>
    lis.filter((li) => { const t = li.querySelector("span")!; return t.getBoundingClientRect().width > li.getBoundingClientRect().width - 14; }).map((li) => li.textContent));
  await expect(insight.getByRole("list", { name: "Turn pipeline" }).locator("li").first()).toBeVisible();
  expect(await cut()).toEqual([]);

  // Drag the edge 200 px left: 600 px, and the debate's rail ends left of it.
  const box = (await edge.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 - 100, box.y + box.height / 2, { steps: 4 });
  await page.mouse.move(box.x + box.width / 2 - 200, box.y + box.height / 2, { steps: 4 });
  await page.mouse.up();
  await expect(edge).toHaveAttribute("aria-valuenow", "600");
  await expect.poll(async () => Math.round((await insight.boundingBox())?.width ?? 0)).toBe(600);
  const rail = page.getByRole("navigation", { name: "Debate timeline" });
  await expect.poll(async () => {
    const r = (await rail.boundingBox())!;
    const d = (await insight.boundingBox())!;
    return r.x + r.width <= d.x + 1;
  }).toBe(true);
  expect(await cut()).toEqual([]);

  // Keys: → narrows by 16, Shift+← widens by 64, Home/End go to the ends (at 1440 the session keeps 800 px, so 640);
  // the replay doesn't step on them.
  const seek = page.getByRole("slider", { name: "Seek" });
  const at = await seek.getAttribute("aria-valuetext");
  await edge.focus();
  await page.keyboard.press("ArrowRight");
  await expect(edge).toHaveAttribute("aria-valuenow", "584");
  await page.keyboard.press("Home");
  await expect(edge).toHaveAttribute("aria-valuenow", "320");
  await page.keyboard.press("Shift+ArrowLeft");
  await expect(edge).toHaveAttribute("aria-valuenow", "384");
  expect(await cut()).toEqual([]);
  await page.keyboard.press("End");
  await expect(edge).toHaveAttribute("aria-valuenow", "640");
  await expect(seek).toHaveAttribute("aria-valuetext", at!);
  // At the widest the debate log still fits beside it (it kept a 608 px minimum and its speeches were cut).
  await expect.poll(async () => {
    const d = (await insight.boundingBox())!;
    const rights = await page.getByRole("log").getByRole("listitem").evaluateAll((li) => li.map((e) => e.getBoundingClientRect().right));
    return Math.max(...rights) <= d.x + 1;
  }).toBe(true);

  // Kept across a reload; a double-click puts it back to 400.
  await page.reload();
  await seekToEnd(page);
  await page.keyboard.press("i");
  await expect(edge).toHaveAttribute("aria-valuenow", "640");
  await edge.dblclick();
  await expect(edge).toHaveAttribute("aria-valuenow", "400");
});
