// World Select keyboard (WLD-01), the World Hub (WLD-05) and the Character Profile tabs (PRF-*).
import { expect, expectHttpError, open, test } from "./fixtures";

test("World Select: ←/→ move between worlds from anywhere, Enter opens the hub", async ({ page }) => {
  await open(page, "/worlds");
  const meridian = page.getByRole("button", { name: /^Meridian Council/ });
  const sunny = page.getByRole("button", { name: /^Sunny Hollow/ });
  await expect(meridian).toBeVisible();

  // Nothing has focus yet: the first → lands on the first card (the footer promises the keys work from anywhere).
  await page.keyboard.press("ArrowRight");
  await expect(meridian).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await expect(sunny).toBeFocused();
  await page.keyboard.press("ArrowLeft");
  await expect(meridian).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Enter");

  await expect(page).toHaveURL(/#\/w\/wld_seedSunnyHollow/);
  await expect(page.getByRole("heading", { name: "SUNNY HOLLOW", level: 1 })).toBeVisible();
});

test("World Select with many worlds: the rail opens at the newest, keys and the wheel scroll only the rail @layout", async ({ page }) => {
  await open(page, "/worlds");
  for (let i = 1; i <= 4; i++) {
    await page.getByRole("button", { name: /New World/ }).click();
    await page.getByLabel("Name", { exact: true }).fill(`Extra World ${i}`);
    await page.getByRole("button", { name: /Create world/ }).click();
    await expect(page.getByRole("heading", { name: `EXTRA WORLD ${i}`, level: 1 })).toBeVisible();
    await page.goBack();
    await expect(page.getByRole("button", { name: /New World/ })).toBeVisible();
  }
  const screenX = () => page.locator("[data-screen=S03]").evaluate((el) => el.scrollLeft);
  const railX = () => page.getByRole("list", { name: "Worlds" }).evaluate((el) => el.scrollLeft);
  const newest = page.getByRole("button", { name: /^Extra World 4/ });
  const create = page.getByRole("button", { name: /New World/ });

  // U-12: the cards arrive in front of "+ New World"; scroll anchoring used to open the rail at its far end.
  await expect(newest).toBeInViewport();
  expect(await railX()).toBe(0);
  await expect(page.getByRole("button", { name: "Scroll worlds right" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Scroll worlds left" })).toHaveCount(0);

  // U-11: End/←/Home move focus and scroll the rail, never the screen (it used to shift sideways, cutting the title).
  await page.keyboard.press("End");
  await expect(create).toBeFocused();
  await expect(create).toBeInViewport({ ratio: 0.8 });
  expect(await screenX()).toBe(0);
  await page.keyboard.press("ArrowLeft");
  await expect(page.getByRole("button", { name: /^Sunny Hollow|^Meridian Council/ }).last()).toBeFocused();
  await page.keyboard.press("Home");
  await expect(newest).toBeFocused();
  await expect.poll(railX).toBe(0);
  expect(await screenX()).toBe(0);

  // A plain vertical wheel reaches the far worlds (the rail has no visible scrollbar).
  await newest.hover();
  await page.mouse.wheel(0, 800);
  await expect.poll(railX).toBeGreaterThan(0);
  await expect(page.getByRole("button", { name: "Scroll worlds left" })).toBeVisible();
  expect(await screenX()).toBe(0);
});

test("World Hub: Roster and Sessions tabs, then a character card opens the profile", async ({ page }) => {
  await open(page, "/w/wld_seedMeridian");
  await expect(page.getByRole("heading", { name: "MERIDIAN COUNCIL", level: 1 })).toBeVisible();

  const rosterTab = page.getByRole("tab", { name: /^Roster/ });
  const sessionsTab = page.getByRole("tab", { name: /^Sessions/ });
  await expect(rosterTab).toHaveAttribute("aria-selected", "true");
  const roster = page.getByRole("tabpanel", { name: /^Roster/ });
  for (const name of ["Amara Okafor", "Mei Tanaka-Ruiz", "Victor Hale"]) {
    await expect(roster.getByRole("button", { name: new RegExp(`^${name}, .*Open profile$`) })).toBeVisible();
  }

  await sessionsTab.click();
  await expect(sessionsTab).toHaveAttribute("aria-selected", "true");
  const sessions = page.getByRole("tabpanel", { name: /^Sessions/ }).getByRole("list", { name: "Sessions" });
  await expect(sessions.getByRole("button", { name: "Debate: Four-day work week", exact: true })).toBeVisible();
  await expect(sessions.getByRole("button", { name: "Three-day headache", exact: true })).toBeVisible();

  await rosterTab.click();
  await roster.getByRole("button", { name: /^Amara Okafor, .*Open profile$/ }).click();
  await expect(page).toHaveURL(/#\/w\/wld_seedMeridian\/c\/chr_seedAmara/);
  await expect(page.getByRole("heading", { name: "Amara Okafor", level: 1 })).toBeVisible();
});

test("World Hub: every World options item can be clicked, below the cover's slanted edge too @layout", async ({ page }) => {
  await open(page, "/w/wld_seedMeridian");
  await page.getByRole("button", { name: "World options" }).click();
  const menu = page.getByRole("menu", { name: "World options" });
  await expect(menu.getByRole("menuitem")).toHaveText(["Edit world", "Session history", "Delete world…"]);
  // The header used to clip the menu at its bottom edge: the last item was drawn under it and could not be hit.
  await menu.getByRole("menuitem", { name: "Delete world…" }).click({ timeout: 3000 });
  const confirm = page.getByRole("dialog", { name: /Delete Meridian Council\?/ });
  await expect(confirm).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(confirm).toBeHidden();
  await expect(page.getByRole("heading", { name: "MERIDIAN COUNCIL", level: 1 })).toBeVisible();
});

test("World Hub: Delete world… removes it; World Select shows the rest without re-reading it", async ({ page }) => {
  // U-27: the hub, still on screen while it left, re-read the deleted world (a 404, caught by the console guard).
  // U-28: the label shows the name in capitals, and typing it that way works (it never matched "Meridian Council").
  await open(page, "/w/wld_seedMeridian");
  await page.getByRole("button", { name: "World options" }).click();
  await page.getByRole("menu", { name: "World options" }).getByRole("menuitem", { name: "Delete world…" }).click();
  const confirm = page.getByRole("dialog", { name: "Delete Meridian Council?" });
  const field = confirm.getByLabel("Type “Meridian Council” to confirm");
  await field.fill("MERIDIAN COUNCI");
  await expect(confirm.getByRole("button", { name: "Delete world" })).toBeDisabled();
  await field.fill("MERIDIAN COUNCIL");
  await confirm.getByRole("button", { name: "Delete world" }).click();
  await expect(page.getByText("Deleted Meridian Council.")).toBeVisible();
  await expect(page).toHaveURL(/#\/worlds$/);
  const rail = page.getByRole("list", { name: "Worlds" });
  await expect(rail.getByRole("button", { name: /^Sunny Hollow/ })).toBeVisible();
  await expect(rail.getByRole("button", { name: /^Meridian Council/ })).toHaveCount(0);
});

test("World Select: with the demo deleted, “Watch a 60-second AI debate” offers to restore it, then plays it", async ({ page }) => {
  // The user's ask (2026-10-22): the button stays, and brings the demo back (Reset demo data) instead of a dead end.
  await open(page, "/w/wld_seedMeridian");
  await page.getByRole("button", { name: "World options" }).click();
  await page.getByRole("menu", { name: "World options" }).getByRole("menuitem", { name: "Delete world…" }).click();
  const confirm = page.getByRole("dialog", { name: "Delete Meridian Council?" });
  await confirm.getByLabel("Type “Meridian Council” to confirm").fill("MERIDIAN COUNCIL");
  await confirm.getByRole("button", { name: "Delete world" }).click();
  await expect(page).toHaveURL(/#\/worlds$/);

  // The app asks for the featured session to learn it is gone: that 404 is the expected answer.
  expectHttpError(page, 404);
  await page.getByRole("button", { name: "▶ Watch a 60-second AI debate" }).click();
  const ask = page.getByRole("dialog", { name: "Bring the demo back?" });
  await expect(ask).toContainText("Worlds, characters and sessions you created stay");
  await ask.getByRole("button", { name: "Restore demo data" }).click();
  await expect(page.getByText("Demo data restored.")).toBeVisible();
  await expect(page).toHaveURL(/#\/w\/wld_seedMeridian\/s\/ses_seedDebate4Day\?replay=1$/);
  await expect(page.getByRole("slider", { name: "Seek" })).toBeVisible();
});

test("Profile: [ and ] step through the six tabs and wrap", async ({ page }) => {
  await open(page, "/w/wld_seedMeridian/c/chr_seedAmara");
  const tabs = page.getByRole("tablist", { name: "Profile sections" });
  const selected = tabs.getByRole("tab", { selected: true });
  await expect(selected).toHaveText("Profile");

  for (const name of ["Gallery", "Theme", "Sessions", "Memory", "Knowledge"]) {
    await page.keyboard.press("]");
    await expect(selected).toHaveText(name);
  }
  await expect(page).toHaveURL(/tab=knowledge/);
  await page.keyboard.press("[");
  await expect(selected).toHaveText("Memory");
  await page.keyboard.press("]");
  await page.keyboard.press("]");
  await expect(selected).toHaveText("Profile");
});

test("Sessions tab: a row's “⋯” menu shows whole, above the rows below, and its last item can be clicked @layout", async ({ page }) => {
  // U-75: the row's slanted clip-path cut the open menu down to a 16 px strip.
  await open(page, "/w/wld_seedSunnyHollow?tab=sessions");
  await page.getByRole("button", { name: "More for Long day" }).click();
  const menu = page.getByRole("menu", { name: "More for Long day" });
  await expect(menu.getByRole("menuitem")).toHaveText(["Open", "Rename", "Export Markdown", "Delete…"]);
  await menu.getByRole("menuitem", { name: "Delete…" }).click({ timeout: 3000 });
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
});

test("Replay from the Sessions tab opens the recording in replay mode", async ({ page }) => {
  await open(page, "/w/wld_seedMeridian?tab=sessions");
  await page.getByRole("button", { name: "Replay Debate: Four-day work week" }).click();
  await expect(page).toHaveURL(/#\/w\/wld_seedMeridian\/s\/ses_seedDebate4Day\?replay=1/);
  await expect(page.getByRole("group", { name: "Replay transport" })).toBeVisible();
  // Replays open with focus on ▶ so Space works immediately.
  await expect(page.getByRole("button", { name: "Play replay (Space)" })).toBeFocused();
});

test("World Select: “Watch a 60-second AI debate” opens the featured replay in one click", async ({ page }) => {
  await open(page, "/worlds");
  await page.getByRole("button", { name: "▶ Watch a 60-second AI debate" }).click();
  await expect(page).toHaveURL(/#\/w\/wld_seedMeridian\/s\/ses_seedDebate4Day\?replay=1$/);
  await expect(page.getByRole("slider", { name: "Seek" })).toBeVisible();
});
