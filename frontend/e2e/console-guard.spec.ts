// The console-clean rule on HTTP (http-client-parity D12, e2e-suite "Console stays clean on both clients"): a 4xx the
// test declared is accepted, anything else still fails the test. HttpClient only: the MockClient makes no requests.
import { clientFor, expect, expectHttpError, open, test } from "./fixtures";

async function fetchFromApp(page: import("@playwright/test").Page, path: string): Promise<number> {
  return page.evaluate(async (p) => (await fetch(p)).status, path);
}

test("a declared 404 from the API keeps the console clean", async ({ page }) => {
  await open(page, "/worlds");
  test.skip(clientFor(page) !== "http", "the MockClient makes no HTTP requests");
  await expect(page.getByRole("list", { name: "Worlds" })).toBeVisible();
  expectHttpError(page, 404);
  expect(await fetchFromApp(page, "/api/v1/worlds/wld_nope")).toBe(404);
});

test("an undeclared 404 from the API fails the test", async ({ page }) => {
  await open(page, "/worlds");
  test.skip(clientFor(page) !== "http", "the MockClient makes no HTTP requests");
  test.fail(true, "the console-clean fixture must reject an undeclared status");
  await expect(page.getByRole("list", { name: "Worlds" })).toBeVisible();
  expect(await fetchFromApp(page, "/api/v1/worlds/wld_nope")).toBe(404);
  await page.waitForTimeout(200);   // let the console line arrive before the fixture checks
});
