// Flow F2: the 8-step character wizard through to the Summon reveal (CHR-*, O04, O15).
import { expect, open, setMockKey, test } from "./fixtures";

test("wizard: seed → AI draft → look → portrait → emotions (skipped) → palette → theme → approve → Summon @layout", async ({ page }) => {
  test.slow(); // eight steps plus two mock generations
  await open(page, "/w/wld_seedMeridian", { speed: 4 });
  await page.getByRole("button", { name: "New Character", exact: true }).click();
  await expect(page).toHaveURL(/\/create\/seed$/);
  await expect(page.getByRole("heading", { name: "Who are we summoning?" })).toBeVisible();

  // Without a key the AI draft is gated; set the mock key from the dev switcher.
  await expect(page.getByRole("button", { name: /Draft with AI/ })).toBeDisabled();
  await setMockKey(page);
  await page.getByRole("textbox", { name: "Seed line" }).fill("Sarah, a doctor");
  await page.getByRole("button", { name: /Draft with AI/ }).click();

  // 02 Profile: the draft fills the form.
  await expect(page.getByRole("heading", { name: "Make them yours" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Name *" })).toHaveValue("Sarah");
  await page.getByRole("button", { name: "Next: Look ▸" }).click();

  // 03 Look → 04 Portrait (first generation per launch asks O04 for a cost check).
  await page.getByRole("button", { name: /^Generate portrait/ }).click();
  const cost = page.getByRole("dialog", { name: "Spend a little?" });
  await expect(cost).toBeVisible();
  await cost.getByRole("button", { name: /^Generate ≈/ }).click();
  await expect(page.getByRole("heading", { name: "Pick a face" })).toBeVisible();
  await page.getByRole("button", { name: "Lock as base" }).click();
  await page.getByRole("button", { name: "Next: Emotions ▸" }).click();

  // 05 Emotions: skip for now.
  await expect(page.getByRole("heading", { name: "Seven faces" })).toBeVisible();
  await page.getByRole("button", { name: "Skip for now" }).click();

  // 06 Palette → 07 Theme → 08 Approve.
  await expect(page.getByRole("radiogroup", { name: "Palette" })).toBeVisible();
  await page.getByRole("button", { name: "Next: Theme ▸" }).click();
  await expect(page.getByRole("heading", { name: "Write the brief" })).toBeVisible();
  await page.getByRole("button", { name: "Next: Approve ▸" }).click();
  await expect(page.getByRole("heading", { name: "Sarah", level: 1 })).toBeVisible();
  await expect(page.getByText("No theme song: the ambient bed plays instead.")).toBeVisible();

  await page.getByRole("button", { name: "Approve & Summon ▸" }).click();
  // O15 Summon reveal: any key skips the ceremony.
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#\/w\/wld_seedMeridian\/c\/chr_[A-Z0-9]+$/);
  await expect(page.getByRole("heading", { name: "Sarah", level: 1 })).toBeVisible();
  await expect(page.getByRole("tablist", { name: "Profile sections" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Chat ▸" })).toBeVisible();
});
