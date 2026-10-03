// Knowledge citations end to end (PRF-10, D-59): [n] chips, the Sources strip, the O28 Source viewer, Insight.
import { expect, logEntry, open, seekToEnd, test } from "./fixtures";

const HEADACHE = "/w/wld_seedMeridian/s/ses_seedAmaraHeadache?replay=1";
const DINNER = "/w/wld_seedSunnyHollow/s/ses_seedDinner?replay=1";

test("1:1 replay: a citation chip opens O28 on the highlighted passage; Esc closes it and returns focus", async ({ page }) => {
  await open(page, HEADACHE);
  await seekToEnd(page);

  const chip = page.getByRole("button", { name: "Source 1: ED triage guidelines, § 2.4. Open source" });
  await chip.click();
  const viewer = page.getByRole("dialog", { name: /ED triage guidelines/ });
  await expect(viewer).toBeVisible();
  const cited = viewer.getByRole("region", { name: "§ 2.4, cited passage" });
  await expect(cited).toBeVisible();
  await expect(cited.locator("mark")).toContainText("Caffeine withdrawal headache");
  await expect(viewer.getByText(/Highlighted: the passage behind \[1\]/)).toBeVisible();
  await expect(viewer.getByRole("button", { name: "Close source viewer" })).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(viewer).toBeHidden();
  await expect(chip).toBeFocused();
});

test("group dinner: Hana's cited line has a Sources strip and its entry opens O28", async ({ page }) => {
  await open(page, DINNER);
  await seekToEnd(page);

  const hana = logEntry(page, "Grandma always said");
  await expect(hana.getByRole("button", { name: /^Source 1: Grandma's recipe notebook, p\. 5/ })).toBeVisible();
  const sources = hana.getByRole("group", { name: "Sources" });
  await expect(sources).toBeVisible();
  await sources.getByRole("button", { name: /^Open Grandma's recipe notebook, p\. 5/ }).click();

  const viewer = page.getByRole("dialog", { name: /Grandma's recipe notebook/ });
  await expect(viewer).toBeVisible();
  await expect(viewer.locator("mark").first()).toContainText("pineapple");
  await viewer.getByRole("button", { name: "Close", exact: true }).click();
  await expect(viewer).toBeHidden();
});

test("Insight drawer: Knowledge separates the cited passage from “retrieved · not used”", async ({ page }) => {
  await open(page, DINNER);
  await seekToEnd(page);
  await logEntry(page, "Grandma always said").getByRole("button", { name: "Open Insight for this message" }).click();

  const insight = page.getByRole("complementary", { name: "Insight" });
  await expect(insight).toBeVisible();
  const knowledge = insight.getByRole("region", { name: "Knowledge" });
  await expect(knowledge).toContainText("1/2 cited");
  await expect(knowledge.getByRole("button", { name: /^Cited \[1\]: Grandma's recipe notebook, p\. 5/ })).toBeVisible();
  const unused = knowledge.getByRole("button", { name: /^Retrieved, not used: Grandma's recipe notebook, p\. 14/ });
  await expect(unused).toBeVisible();
  await expect(unused).toContainText("retrieved · not used");

  // The keyboard toggle closes it again.
  await page.keyboard.press("i");
  await expect(insight).toBeHidden();
});

test("group dinner at 1280×720: with Insight open every speaker stays visible beside the drawer @layout", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await open(page, DINNER);
  await seekToEnd(page);
  await page.keyboard.press("i");
  const insight = page.getByRole("complementary", { name: "Insight" });
  await expect(insight).toBeVisible();
  await expect(page.getByRole("button", { name: "Insight", exact: true })).toHaveAttribute("aria-pressed", "true");

  // Let the drawer finish sliding in before measuring: its left edge must stop moving.
  let last = -1;
  await expect
    .poll(async () => {
      const x = (await insight.boundingBox())?.x ?? -1;
      const settled = x === last && x < 1280;
      last = x;
      return settled;
    })
    .toBe(true);
  const drawerLeft = last;

  for (const name of [/^Hana Morisaki, /, /^Rin Morisaki, /, /^Takeshi Morisaki, /]) {
    const portrait = page.getByRole("region", { name: /^Cast/ }).getByRole("button", { name });
    await expect(portrait).toBeVisible();
    const box = (await portrait.boundingBox())!;
    expect(box.x + box.width, `${name} must end left of the Insight drawer`).toBeLessThanOrEqual(drawerLeft + 1);
  }
  // The latest cited line and its Sources strip are still on screen.
  await expect(logEntry(page, "Grandma always said").getByRole("group", { name: "Sources" })).toBeInViewport();
});
