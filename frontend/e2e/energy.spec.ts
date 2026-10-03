// Energy top-up (ENG-05, D-76): top-ups cost nothing themselves but are bounded by today's budget headroom;
// a refusal is explained inside the dialog and leaves the energy bar unchanged.
import { expect, open, setMockKey, test } from "./fixtures";

test("top-up refused at the daily cap: the dialog explains why and stays open", async ({ page }) => {
  await open(page, "/w/wld_seedSunnyHollow/c/chr_seedHana");
  await setMockKey(page);
  // Spend = cap (MockSwitcher scenario), so no headroom is left for a top-up.
  await page.keyboard.press("Control+Shift+D");
  const panel = page.getByRole("complementary", { name: /MOCK STATE/ });
  await panel.getByRole("button", { name: /Daily cap reached/ }).click();
  await panel.getByRole("button", { name: "Close", exact: true }).click();

  await page.getByRole("button", { name: "⚡ Top up" }).click();
  const dialog = page.getByRole("dialog", { name: /Give Hana \+500 ⚡\?/ });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("today's budget headroom");
  await dialog.getByRole("button", { name: "Top up", exact: true }).click();

  await expect(dialog.getByRole("alert")).toContainText("Today's budget is reached.");
  await expect(dialog.getByRole("alert")).toContainText("Top-ups can only use budget left today");
  await expect(dialog).toBeVisible();
});
