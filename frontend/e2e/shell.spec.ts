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
