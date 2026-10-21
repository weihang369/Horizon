// World Select keyboard (WLD-01), the World Hub (WLD-05) and the Character Profile tabs (PRF-*).
import { expect, open, test } from "./fixtures";

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
