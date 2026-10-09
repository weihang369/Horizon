// Character Profile: Knowledge tab (PRF-10) and Theme tab (PRF theme track).
import { expect, open, test } from "./fixtures";

test("Knowledge tab: Amara's source cards open the O28 Source viewer", async ({ page }) => {
  await open(page, "/w/wld_seedMeridian/c/chr_seedAmara?tab=knowledge");
  const panel = page.getByRole("tabpanel", { name: "Knowledge" });
  await expect(panel.getByText("2 sources · cited 6× in conversations")).toBeVisible();
  await expect(panel.getByRole("button", { name: "Open Meridian Shift Fatigue Review 2025.pdf" })).toBeVisible();

  const card = panel.getByRole("button", { name: "Open ED triage guidelines.pdf" });
  await card.click();
  const viewer = page.getByRole("dialog", { name: /ED triage guidelines/ });
  await expect(viewer).toBeVisible();
  await expect(viewer.getByText("End of indexed passages · 6 of 6")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(viewer).toBeHidden();
  await expect(card).toBeFocused();
});

test("Knowledge tab: Mei's unreadable document shows the reason and a Retry button", async ({ page }) => {
  await open(page, "/w/wld_seedMeridian/c/chr_seedMei?tab=knowledge");
  const failed = page.getByRole("tabpanel", { name: "Knowledge" }).getByRole("listitem").filter({ hasText: "Working-time pilots appendix.docx" });
  await expect(failed).toContainText("failed");
  await expect(failed).toContainText("This document is password-protected.");
  await expect(failed.getByRole("button", { name: "↻ Retry" })).toBeVisible();
});

test("Knowledge tab: Paste text adds a source that indexes and then opens in the Source viewer", async ({ page }) => {
  await open(page, "/w/wld_seedSunnyHollow/c/chr_seedHana?tab=knowledge");
  const panel = page.getByRole("tabpanel", { name: "Knowledge" });
  await panel.getByRole("button", { name: "Paste text", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: /from pasted text/ });
  await expect(dialog.getByRole("button", { name: "Add" })).toBeDisabled();
  await dialog.getByLabel("Title", { exact: true }).fill("Tea notes");
  await dialog.getByLabel("Text", { exact: true }).fill("Steep for three minutes.\n\nThen pour slowly.");
  await dialog.getByRole("button", { name: "Add" }).click();
  await expect(dialog).toBeHidden();
  const card = panel.getByRole("button", { name: "Open Tea notes" });
  await expect(card).toBeVisible({ timeout: 10_000 });
  await card.click();
  await expect(page.getByRole("dialog", { name: /Tea notes/ })).toBeVisible();
});

test("Theme tab renders the theme player with a working play/pause control @layout", async ({ page }) => {
  await open(page, "/w/wld_seedMeridian/c/chr_seedAmara");
  await page.getByRole("tab", { name: "Theme" }).click();
  const panel = page.getByRole("tabpanel", { name: "Theme" });
  await expect(panel.getByRole("heading", { name: "Amara's Theme" })).toBeVisible();
  await expect(panel.getByRole("region", { name: "Liner notes" })).toBeVisible();

  const control = panel.getByRole("button", { name: /^(Play|Pause) Amara's Theme$/ });
  await expect(control).toBeVisible();
  const before = await control.getAttribute("aria-pressed");
  await control.click();
  await expect(control).toHaveAttribute("aria-pressed", before === "true" ? "false" : "true");
  await control.click();
  await expect(control).toHaveAttribute("aria-pressed", before ?? "false");
});
