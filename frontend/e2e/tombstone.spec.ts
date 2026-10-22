// Character delete leaves a tombstone (D-70, rev 1.3): the character leaves the roster, but sessions they spoke in
// still open and show their name. D-117: no shipped session has a deletable (non-seed) speaker any more, so the test
// makes its own: a short 1:1 with Kenji, then deletes him.
import { expect, open, setKey, test } from "./fixtures";

test("a deleted character's lines still render in an old session", async ({ page }) => {
  test.slow();   // a real reply on the HTTP backend
  await open(page, "/w/wld_seedMeridian/c/chr_mockKenji");
  await setKey(page);
  await page.getByRole("button", { name: "Chat ▸" }).click();
  const input = page.getByRole("textbox", { name: "Talk to Kenji" });
  await input.fill("Morning, Kenji. What are you working on?");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Stop the reply (Ctrl+.)" })).toBeHidden({ timeout: 30_000 });
  await expect(page.getByRole("log").getByRole("listitem").filter({ has: page.getByRole("button", { name: "Regenerate reply" }) })).toHaveCount(1);
  const session = new URL(page.url()).hash;

  await open(page, "/w/wld_seedMeridian/c/chr_mockKenji");
  await page.getByRole("button", { name: "Archive", exact: true }).click();
  await expect(page.getByText(/Kenji Ito archived/)).toBeVisible();

  await open(page, "/w/wld_seedMeridian?filter=archived");
  await page.getByRole("button", { name: "Delete permanently" }).click();
  const confirm = page.getByRole("dialog", { name: /Delete Kenji Ito permanently\?/ });
  await confirm.getByLabel("Type “Kenji Ito” to confirm").fill("Kenji Ito");
  await confirm.getByRole("button", { name: "Delete permanently" }).click();
  await expect(page.getByText("Kenji Ito was deleted.")).toBeVisible();
  await expect(page.getByText("Archived · 0")).toBeVisible();

  await open(page, session);
  const log = page.getByRole("log");
  await expect(log.getByRole("listitem").filter({ hasText: "Kenji" }).first()).toBeVisible();
});
