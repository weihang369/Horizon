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
