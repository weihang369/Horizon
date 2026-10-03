// Flow F1 (first run) and the intro replays (APP-04).
import { expect, open, pressStartOnTitle, test } from "./fixtures";

test("first visit: title → five onboarding cards → World Select; the second launch skips the intro @layout", async ({ page, context }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "HORIZON", level: 1 })).toBeVisible();
  await pressStartOnTitle(page);

  const steps = page.getByRole("list", { name: /Step \d of 5/ });
  for (const [n, title] of [[1, "WORLDS"], [2, "CHARACTERS"], [3, "SESSIONS"], [4, "ENERGY"]] as const) {
    await expect(page).toHaveURL(new RegExp(`#/onboarding/${n}$`));
    await expect(steps).toHaveAccessibleName(`Step ${n} of 5`);
    await expect(page.getByRole("heading", { name: title, level: 1 })).toBeVisible();
    await page.getByRole("button", { name: "Next ▸" }).click();
  }

  await expect(page.getByRole("heading", { name: "YOUR KEY", level: 1 })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "OpenRouter key" })).toBeVisible();
  await page.getByRole("button", { name: "Explore demo first" }).click();

  await expect(page).toHaveURL(/#\/worlds$/);
  const worlds = page.getByRole("list", { name: "Worlds" });
  await expect(worlds.getByRole("button", { name: /^Meridian Council/ })).toBeVisible();
  await expect(worlds.getByRole("button", { name: /^Sunny Hollow/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^DEMO MODE/ })).toBeVisible();

  // Returning visitor (a new tab in the same browser profile): the title goes straight to World Select.
  const again = await context.newPage();
  await again.goto("/");
  await pressStartOnTitle(again);
  await expect(again).toHaveURL(/#\/worlds$/);
});

test("“Skip intro” jumps to the key step", async ({ page }) => {
  await page.goto("/");
  await pressStartOnTitle(page);
  await page.getByRole("button", { name: "Skip intro" }).click();
  await expect(page.getByRole("heading", { name: "YOUR KEY", level: 1 })).toBeVisible();
});

test("“How it works” on World Select and in the Esc menu both replay the intro", async ({ page }) => {
  await open(page, "/worlds");
  await page.getByRole("navigation", { name: "Shell" }).getByRole("button", { name: "How it works" }).click();
  await expect(page).toHaveURL(/#\/onboarding\/1$/);
  await expect(page.getByRole("heading", { name: "WORLDS", level: 1 })).toBeVisible();

  await page.getByRole("button", { name: "Skip intro" }).click();
  await page.getByRole("button", { name: "Explore demo first" }).click();
  await expect(page.getByRole("list", { name: "Worlds" })).toBeVisible();

  await page.keyboard.press("Escape");
  const menu = page.getByRole("dialog", { name: "Paused" });
  await expect(menu).toBeVisible();
  await menu.getByRole("button", { name: /^How it works/ }).click();
  await expect(menu).toBeHidden();
  await expect(page).toHaveURL(/#\/onboarding\/1$/);
  await expect(page.getByRole("list", { name: "Step 1 of 5" })).toBeVisible();
});
