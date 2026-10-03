// Character delete leaves a tombstone (D-70, rev 1.3): the character leaves the roster, but sessions they spoke in
// still open and show their name.
import { expect, open, test } from "./fixtures";

test("a deleted character's lines still render in an old session", async ({ page }) => {
  await open(page, "/w/wld_seedMeridian/c/chr_mockElena");
  await page.getByRole("button", { name: "Archive", exact: true }).click();
  await expect(page.getByText(/Elena Vasquez archived/)).toBeVisible();

  await open(page, "/w/wld_seedMeridian?filter=archived");
  await page.getByRole("button", { name: "Delete permanently" }).click();
  const confirm = page.getByRole("dialog", { name: /Delete Elena Vasquez permanently\?/ });
  await confirm.getByLabel("Type “Elena Vasquez” to confirm").fill("Elena Vasquez");
  await confirm.getByRole("button", { name: "Delete permanently" }).click();
  await expect(page.getByText("Elena Vasquez was deleted.")).toBeVisible();
  await expect(page.getByText("Archived · 0")).toBeVisible();

  await open(page, "/w/wld_seedMeridian/s/ses_mockTooCloseExams");
  const log = page.getByRole("log");
  await expect(log.getByRole("listitem").filter({ hasText: "Elena" }).first()).toBeVisible();
});
