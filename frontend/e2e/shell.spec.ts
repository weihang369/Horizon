// Global shell: the shortcuts sheet (O20) and the desktop guard (O19, APP-06).
import { expect, open, test } from "./fixtures";

test("? opens the keyboard shortcuts sheet and Esc closes it", async ({ page }) => {
  await open(page, "/worlds");
  await expect(page.getByRole("list", { name: "Worlds" })).toBeVisible();
  await page.keyboard.press("Shift+?");
  const sheet = page.getByRole("dialog", { name: "Keyboard shortcuts" });
  await expect(sheet).toBeVisible();
  for (const region of ["Anywhere", "Sessions", "Composer"]) {
    await expect(sheet.getByRole("region", { name: region })).toBeVisible();
  }
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();
  // Esc closed only the sheet; it did not also open the pause menu.
  await expect(page.getByRole("dialog", { name: "Paused" })).toBeHidden();
});

test("Pause menu: a click off the red slab resumes; a click on the slab keeps it open @layout", async ({ page }) => {
  await open(page, "/w/wld_seedMeridian");
  await expect(page.getByRole("heading", { name: "MERIDIAN COUNCIL", level: 1 })).toBeVisible();
  const menu = page.getByRole("dialog", { name: "Paused" });
  const { width: w, height: h } = page.viewportSize()!;
  // The slab is 54% wide at the top and 42% at the bottom (clip-path): probe both sides of its slanted edge.
  const pause = async () => {
    await page.keyboard.press("Escape");
    await expect(menu).toBeVisible();
    await page.waitForTimeout(400); // the slab's wipe-in
  };
  await pause();
  for (const [x, y] of [[w * 0.3, h - 12], [w * 0.4, h - 12], [w * 0.52, 12]]) {
    await page.mouse.click(x, y);
    await expect(menu, `click on the slab at ${x},${y}`).toBeVisible();
  }
  for (const [x, y] of [[w * 0.45, h - 12], [w * 0.9, h / 2]]) {
    await page.mouse.click(x, y);
    await expect(menu, `click off the slab at ${x},${y}`).toBeHidden();
    await pause();
  }
  await menu.getByText("CURRENT WORLD").click(); // the world card on the dark side is information, not a button
  await expect(menu).toBeHidden();
  await expect(page).toHaveURL(/#\/w\/wld_seedMeridian$/);
});

test.describe("desktop guard", () => {
  test.use({ viewport: { width: 1000, height: 600 } });

  test("a 1000×600 window shows the “Desktop only” notice", async ({ page }) => {
    await open(page, "/worlds");
    const guard = page.getByRole("alertdialog", { name: "DESKTOP ONLY" });
    await expect(guard).toBeVisible();
    await expect(guard).toContainText("1000 × 600 · need 1280 × 720");

    // Widening to the minimum removes it.
    await page.setViewportSize({ width: 1280, height: 720 });
    await expect(guard).toBeHidden();
    await expect(page.getByRole("list", { name: "Worlds" })).toBeVisible();
  });
});
