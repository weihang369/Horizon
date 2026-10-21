// Knowledge citations end to end (PRF-10, D-59): [n] chips, the Sources strip, the O28 Source viewer, Insight.
import { expect, logEntry, open, seekToEnd, test } from "./fixtures";

const HEADACHE = "/w/wld_seedMeridian/s/ses_seedAmaraHeadache?replay=1";
const DINNER = "/w/wld_seedSunnyHollow/s/ses_seedDinner?replay=1";

test("1:1 replay: a citation chip opens O28 on the highlighted passage; Esc closes it and returns focus", async ({ page }) => {
  await open(page, HEADACHE);
  await seekToEnd(page);

  const chip = page.getByRole("button", { name: "Source 1: ED triage guidelines, p. 3. Open source" }).first();
  await chip.click();
  const viewer = page.getByRole("dialog", { name: /ED triage guidelines/ });
  await expect(viewer).toBeVisible();
  const cited = viewer.getByRole("region", { name: "p. 3, cited passage" });
  await expect(cited).toBeVisible();
  await expect(cited).toContainText("Escalate any headache that is sudden and severe");
  await expect(viewer.getByText(/Highlighted: the passage behind \[1\]/)).toBeVisible();
  await expect(viewer.getByRole("button", { name: "Close source viewer" })).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(viewer).toBeHidden();
  await expect(chip).toBeFocused();
});

test("1:1 replay: the Sources entry for three markers in one document marks all three and jumps between them (U-37)", async ({ page }) => {
  await open(page, HEADACHE);
  await seekToEnd(page);

  await page.getByRole("group", { name: "Sources" }).last().getByRole("button", { name: /^Open ED triage guidelines, p\. 3 \(markers 1, 2, 3\)/ }).click();
  const viewer = page.getByRole("dialog", { name: /ED triage guidelines/ });
  await expect(viewer.getByRole("region", { name: "p. 3, cited passage" })).toHaveCount(3);
  for (const [n, text] of [[1, "3.1 Escalate at once"], [2, "3.2 Other warning signs"], [3, "3.3 Same-day review"]] as const)
    await expect(viewer.getByRole("region", { name: "p. 3, cited passage" }).filter({ hasText: `[${n}] cited` })).toContainText(text);
  await expect(viewer.getByText("Highlighted: the passages behind [1] [2] [3].")).toBeVisible();

  const marks = viewer.getByRole("group", { name: "Cited passages" });
  await expect(marks.getByRole("button", { name: "Jump to [1], p. 3" })).toHaveAttribute("aria-pressed", "true");
  await marks.getByRole("button", { name: "Jump to [3], p. 3" }).click();
  await expect(marks.getByRole("button", { name: "Jump to [3], p. 3" })).toHaveAttribute("aria-pressed", "true");
  const third = viewer.locator('section[aria-current="true"]');
  await expect(third).toContainText("3.3 Same-day review");
  await expect(third).toBeInViewport();
  await expect(viewer.getByRole("button", { name: "▸ Jump to [3]" })).toBeVisible();

  // a single chip still opens on its own passage only
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Source 2: ED triage guidelines, p. 3. Open source" }).first().click();
  await expect(viewer.getByRole("region", { name: "p. 3, cited passage" })).toHaveCount(1);
  await expect(viewer.getByRole("region", { name: "p. 3, cited passage" })).toContainText("[2] cited");
  await expect(viewer.getByRole("group", { name: "Cited passages" })).toHaveCount(0);
});

test("group dinner: Hana's cited line has a Sources strip and its entry opens O28", async ({ page }) => {
  await open(page, DINNER);
  await seekToEnd(page);

  const hana = logEntry(page, "arguments about it are practically the appetizer");
  await expect(hana.getByRole("button", { name: /^Source 1: Grandma's recipe notebook, ¶ 2/ }).first()).toBeVisible();
  const sources = hana.getByRole("group", { name: "Sources" });
  await expect(sources).toBeVisible();
  await sources.getByRole("button", { name: /^Open Grandma's recipe notebook, ¶ 2/ }).click();

  const viewer = page.getByRole("dialog", { name: /Grandma's recipe notebook/ });
  await expect(viewer).toBeVisible();
  await expect(viewer.getByRole("region", { name: /cited passage/ })).toContainText("Strawberry daifuku");
  await viewer.getByRole("button", { name: "Close", exact: true }).click();
  await expect(viewer).toBeHidden();
});

test("Insight drawer: Knowledge separates the cited passage from “retrieved · not used”", async ({ page }) => {
  await open(page, DINNER);
  await seekToEnd(page);
  await logEntry(page, "arguments about it are practically the appetizer").getByRole("button", { name: "Open Insight for this message" }).click();

  const insight = page.getByRole("complementary", { name: "Insight" });
  await expect(insight).toBeVisible();
  const knowledge = insight.getByRole("region", { name: "Knowledge" });
  await expect(knowledge).toContainText("1/3 cited");
  await expect(knowledge.getByRole("button", { name: /^Cited \[1\]: Grandma's recipe notebook, ¶ 2/ })).toBeVisible();
  const unused = knowledge.getByRole("button", { name: /^Retrieved, not used: Grandma's recipe notebook, ¶ 1/ });
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
  // The latest line is still on screen, left of the drawer (the cited line is two lines up in this recording).
  const latest = page.getByRole("log").getByRole("listitem").last();
  await expect(latest).toBeInViewport();
  const lb = (await latest.boundingBox())!;
  expect(lb.x + lb.width, "the latest line must end left of the Insight drawer").toBeLessThanOrEqual(drawerLeft + 1);
});
