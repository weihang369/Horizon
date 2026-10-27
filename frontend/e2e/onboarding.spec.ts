// Flow F1 (first run) and the intro replays (APP-04).
import { clientFor, expect, open, pressStartOnTitle, test } from "./fixtures";

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
  if (clientFor(page) === "mock") {
    // the online demo never asks for a key: the notice and the run-locally link instead (2026-10-20)
    await expect(page.getByText(/This online demo never uses a key/)).toBeVisible();
    await expect(page.getByRole("textbox", { name: "OpenRouter key" })).toHaveCount(0);
    await page.getByRole("button", { name: "Explore the demo ▸" }).click();
  } else {
    await expect(page.getByRole("textbox", { name: "OpenRouter key" })).toBeVisible();
    await page.getByRole("button", { name: "Explore demo first" }).click();
  }

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
  await page.getByRole("button", { name: clientFor(page) === "mock" ? "Explore the demo ▸" : "Explore demo first" }).click();
  await expect(page.getByRole("list", { name: "Worlds" })).toBeVisible();

  await page.keyboard.press("Escape");
  const menu = page.getByRole("dialog", { name: "Paused" });
  await expect(menu).toBeVisible();
  await menu.getByRole("button", { name: /^How it works/ }).click();
  await expect(menu).toBeHidden();
  await expect(page).toHaveURL(/#\/onboarding\/1$/);
  await expect(page.getByRole("list", { name: "Step 1 of 5" })).toBeVisible();
});

test("intro: →/← step through the cards, and a quick second → is not lost mid-transition", async ({ page }) => {
  await open(page, "/onboarding/1");
  await expect(page.getByRole("heading", { name: "WORLDS", level: 1 })).toBeVisible();
  // Two presses inside the ~300 ms slash: the second used to re-request card 2 (U-11).
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await expect(page).toHaveURL(/#\/onboarding\/3$/);
  await expect(page.getByRole("heading", { name: "SESSIONS", level: 1 })).toBeVisible();
  await page.keyboard.press("ArrowLeft");
  await expect(page).toHaveURL(/#\/onboarding\/2$/);
  await expect(page.getByRole("heading", { name: "CHARACTERS", level: 1 })).toBeVisible();
  // Esc on the intro is not the pause menu.
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Paused" })).toHaveCount(0);
});
