// A failed read is not a missing thing, and it is not stuck: Settings → Display's live preview (Hana) after its load
// fails once (U-24: it said "Preview needs the seed character Hana" for a Hana who was there, until a full reload).
// HttpClient only: the failure is staged on the network, and the MockClient makes no requests, so playwright.config.ts
// runs this file on http-desktop only.
import { expect, expectHttpError, open, test } from "./fixtures";
import type { Page } from "@playwright/test";

/** The next `times` reads of Hana answer 429 rate_limited (a declared 4xx; the client doesn't retry it). */
async function failHana(page: Page, times: number): Promise<void> {
  let left = times;
  expectHttpError(page, 429);
  await page.route("**/api/v1/characters/chr_seedHana", (route) => {
    if (left <= 0 || route.request().method() !== "GET") return route.fallback();
    left -= 1;
    return route.fulfill({ status: 429, json: { error: { code: "rate_limited", message: "Too many requests.", retryable: true } } });
  });
}

test("Display preview: a failed load offers Retry, and opening the tab again loads Hana", async ({ page }) => {
  const preview = page.getByRole("complementary", { name: "Live preview" });
  const portrait = preview.locator("[data-vfx]");
  await failHana(page, 1);
  await open(page, "/settings/display");
  await expect(preview).toContainText("Couldn't load the preview.");
  await expect(preview).not.toContainText("needs the seed character");

  // Away and back: the cached failure is retried on the way in.
  await page.getByRole("tab", { name: /Chat/ }).click();
  await page.getByRole("tab", { name: /Display/ }).click();
  await expect(portrait.first()).toBeVisible();

  // A fresh load that fails again: Retry loads her in place.
  await failHana(page, 1);
  await page.reload();
  await expect(preview).toContainText("Couldn't load the preview.");
  await preview.getByRole("button", { name: "Retry" }).click();
  await expect(portrait.first()).toBeVisible();
});
