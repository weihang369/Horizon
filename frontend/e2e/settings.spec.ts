// Settings → Connection (SET-01, APP-09): every control, on both clients. A key starting `sk-or-bad` is rejected by the
// MockClient and by the test backend's fake OpenRouter alike.
import { E2E_KEY, expect, expectHttpError, open, setKey, test } from "./fixtures";

test("Connection: Show, Save (empty, wrong, rejected, good), Test, Clear and the key link all work", async ({ page }) => {
  await open(page, "/settings");
  const status = page.locator("[data-status]");
  const field = page.getByLabel(/^(Key|Replace key)$/);
  const save = page.getByRole("button", { name: "Save key" });
  const testBtn = page.getByRole("button", { name: /Test connection$/ });
  const clear = page.getByRole("button", { name: "Clear key" });
  await expect(status).toHaveAttribute("data-status", "missing");
  await expect(page.getByLabel("Key", { exact: true })).toBeVisible();
  await expect(clear).toHaveCount(0);

  // The key link opens OpenRouter in a new tab.
  const link = page.getByRole("link", { name: /openrouter\.ai\/keys/ });
  await expect(link).toHaveAttribute("href", "https://openrouter.ai/keys");
  await expect(link).toHaveAttribute("target", "_blank");

  // Without a key, Test explains what's missing instead of calling anything.
  await testBtn.click();
  const needKey = page.getByRole("dialog", { name: /Add your OpenRouter key/ });
  await expect(needKey).toContainText("Testing the connection needs a key");
  await needKey.getByRole("button", { name: "Not now" }).click();
  await expect(needKey).toBeHidden();

  // Empty and wrong-prefix keys never leave the page.
  await save.click();
  await expect(page.getByText("Paste a key first.")).toBeVisible();
  await field.fill("abc");
  await expect(page.getByText("Paste a key first.")).toBeHidden(); // typing clears the error
  await save.click();
  await expect(page.getByText("OpenRouter keys start with sk-or-.")).toBeVisible();

  // Show / Hide only flips the field's visibility.
  await field.fill("sk-or-bad-e2e-0001");
  await expect(field).toHaveAttribute("type", "password");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(field).toHaveAttribute("type", "text");
  await expect(page.getByRole("button", { name: "Hide" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Hide" }).click();
  await expect(field).toHaveAttribute("type", "password");
  await expect(field).toHaveValue("sk-or-bad-e2e-0001");

  // A rejected key: the status says so, Test fails with a Retry, Clear appears.
  await save.click();
  await expect(page.getByText("That key was rejected by OpenRouter.")).toBeVisible();
  await expect(status).toHaveAttribute("data-status", "invalid");
  await expect(status).toContainText("KEY REJECTED");
  expectHttpError(page, 401); // the test backend's Test connection answers the rejected key with a 401
  await testBtn.click();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  await expect(page.getByText(/Connected · \d+ ms/)).toHaveCount(0);

  // A good key (Enter submits too): live, masked to its last 4, the field empties, Test reports latency and balance.
  await field.fill(E2E_KEY);
  await field.press("Enter");
  await expect(page.getByText("Key saved on this machine. Demo mode is off.")).toBeVisible();
  await expect(status).toHaveAttribute("data-status", "set");
  await expect(status).toContainText(`sk-or-…${E2E_KEY.slice(-4)}`);
  await expect(field).toHaveValue("");
  await expect(page.getByLabel("Replace key", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toHaveCount(0);
  await testBtn.click();
  await expect(page.getByRole("status").filter({ hasText: /Connected · \d+ ms · balance \$\d/ })).toBeVisible();

  // Clear: back to demo mode, and the Clear row goes away.
  await clear.click();
  await expect(page.getByText("Key cleared. Back to demo mode.")).toBeVisible();
  await expect(status).toHaveAttribute("data-status", "missing");
  await expect(clear).toHaveCount(0);
  await expect(page.getByText(/Connected · \d+ ms/)).toHaveCount(0);
});

test("Chat: every default is saved, and new 1:1s, groups and debates start from it", async ({ page }) => {
  await open(page, "/settings/chat");
  const radio = (group: string, name: string) => page.getByRole("radiogroup", { name: group }).getByRole("radio", { name });
  const toggle = (name: string) => page.getByRole("switch", { name });
  await expect(radio("Emotion mode", "Auto")).toHaveAttribute("aria-checked", "true");
  await expect(radio("Group responders", "Auto")).toHaveAttribute("aria-checked", "true");
  await expect(toggle("Debate auto-advance")).toHaveAttribute("aria-checked", "true");
  await expect(toggle("Readable Mode by default")).toHaveAttribute("aria-checked", "false");
  await expect(toggle("Speaker cut-ins")).toHaveAttribute("aria-checked", "true");

  await radio("Emotion mode", "Manual").click();
  await radio("Group responders", "Everyone").click();
  await radio("Group responders", "Mentioned").click();
  for (const name of ["Debate auto-advance", "Readable Mode by default", "Speaker cut-ins"]) await toggle(name).click();
  // Saved, not just shown: a reload reads them back (the first four from the backend, cut-ins from this browser).
  await expect(toggle("Readable Mode by default")).toHaveAttribute("aria-checked", "true");
  await page.reload();
  await expect(radio("Emotion mode", "Manual")).toHaveAttribute("aria-checked", "true");
  await expect(radio("Group responders", "Mentioned")).toHaveAttribute("aria-checked", "true");
  await expect(toggle("Debate auto-advance")).toHaveAttribute("aria-checked", "false");
  await expect(toggle("Readable Mode by default")).toHaveAttribute("aria-checked", "true");
  await expect(toggle("Speaker cut-ins")).toHaveAttribute("aria-checked", "false");
  await setKey(page);

  // Group and debate Setup start from the same defaults (it used to start at Auto / Auto whatever Settings said).
  await page.evaluate(() => { location.hash = "#/w/wld_seedMeridian/setup/config?mode=group&cast=chr_seedAmara,chr_seedMei"; });
  await expect(radio("Faces", "MANUAL")).toHaveAttribute("aria-checked", "true");
  await expect(radio("Who responds", "Mentioned only")).toHaveAttribute("aria-checked", "true");
  await page.getByRole("button", { name: "Start ▸" }).click();
  await expect(page.getByRole("button", { name: /^Who responds.*Mentioned only/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Readable", exact: true })).toHaveAttribute("aria-pressed", "true");

  // A debate: auto-advance off, so Next steps the turns by hand.
  await page.evaluate(() => { location.hash = "#/w/wld_seedMeridian/setup/config?mode=debate&cast=chr_seedAmara,chr_seedMei"; });
  await expect(radio("Faces", "MANUAL")).toHaveAttribute("aria-checked", "true");
  await page.getByRole("textbox", { name: "Motion" }).fill("This house would ban homework");
  await page.getByRole("button", { name: "Start ▸" }).click();
  await expect(page.getByRole("toolbar", { name: "Debate steering" }).getByRole("button", { name: /^Next/ })).toHaveAttribute("title", "Next turn (→)");

  // A new 1:1, last: it opens with a streamed greeting, and only one session streams at a time. Victor has none yet.
  await page.evaluate(() => { location.hash = "#/w/wld_seedMeridian"; });
  await page.getByRole("listitem").filter({ hasText: "Victor Hale" }).getByRole("button", { name: "Chat" }).click();
  await expect(page.getByRole("radiogroup", { name: "Emotion mode" }).getByRole("radio", { name: "Manual" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("button", { name: "Readable", exact: true })).toHaveAttribute("aria-pressed", "true");
});

test("Display: every control changes the page, the preview follows reduced motion, Presenter Mode hides the key", async ({ page }) => {
  await open(page, "/settings/display");
  const root = page.locator("html");
  const preview = page.getByRole("complementary", { name: "Live preview" });
  const radio = (group: string, name: string) => page.getByRole("radiogroup", { name: group }).getByRole("radio", { name, exact: true });
  const toggle = (name: string) => page.getByRole("switch", { name });
  const token = (name: string) => page.evaluate((n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim(), name);
  await expect(preview.locator("[data-vfx]").first()).toHaveAttribute("data-vfx", "full");

  for (const v of ["off", "subtle", "full"]) {
    await radio("Emotion VFX", v[0].toUpperCase() + v.slice(1)).click();
    await expect(root).toHaveAttribute("data-vfx", v);
    await expect(preview.locator("[data-vfx]").first()).toHaveAttribute("data-vfx", v);
  }
  for (const [v, peak] of [["Off", "0"], ["Low", "0.35"]]) {
    await radio("Flash intensity", v).click();
    await expect.poll(() => token("--flash-peak")).toBe(peak);
  }
  await radio("Flash intensity", "Full").click();
  await toggle("Parallax").click();
  await expect(root).toHaveAttribute("data-parallax", "off");
  await toggle("Parallax").click();
  await expect(root).toHaveAttribute("data-parallax", "on");
  for (const [v, px] of [["S", "14px"], ["L", "18px"], ["M", "16px"]]) {
    await radio("Text size", v).click();
    await expect.poll(() => token("--text-body")).toBe(px);
    await expect(preview).toContainText(`Text size ${v}`);
  }

  // Reduced motion turns the VFX off, so the preview's line says so too (it used to say "vfx full").
  await radio("Reduced motion", "On").click();
  await expect(root).toHaveAttribute("data-motion", "reduced");
  await expect(root).toHaveAttribute("data-vfx", "off");
  await expect(preview).toContainText(/motion reduced · vfx off/i);
  await radio("Reduced motion", "Off").click();
  await expect(preview).toContainText(/motion full · vfx full/i);

  // Presenter Mode: text L, and Connection shows neither the key's last four nor a Show button.
  await setKey(page);
  await page.evaluate(() => { location.hash = "#/settings/connection"; });
  await expect(page.locator("[data-status]")).toContainText("sk-or-…0001");
  await page.evaluate(() => { location.hash = "#/settings/display"; });
  await toggle("Presenter Mode").click();
  await expect(root).toHaveAttribute("data-text-size", "l");
  await page.evaluate(() => { location.hash = "#/settings/connection"; });
  await expect(page.locator("[data-status]")).toContainText("KEY SET");
  await expect(page.locator("[data-status]")).not.toContainText("0001");
  await expect(page.getByRole("button", { name: "Show" })).toHaveCount(0);
});
