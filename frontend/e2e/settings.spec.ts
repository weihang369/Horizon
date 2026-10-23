// Settings → Connection (SET-01, APP-09): every control, on both clients. A key starting `sk-or-bad` is rejected by the
// MockClient and by the test backend's fake OpenRouter alike.
import { E2E_KEY, expect, expectHttpError, genTimeout, open, setKey, test } from "./fixtures";

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

  // Presenter Mode: text L (the Text size control locked on L), and Connection shows neither the key's last four nor a Show button.
  await setKey(page);
  await page.evaluate(() => { location.hash = "#/settings/connection"; });
  await expect(page.locator("[data-status]")).toContainText("sk-or-…0001");
  await page.evaluate(() => { location.hash = "#/settings/display"; });
  await toggle("Presenter Mode").click();
  await expect(root).toHaveAttribute("data-text-size", "l");
  // The Text size control shows the L it forces, locked; turning Presenter off gives back the M chosen above.
  await expect(radio("Text size", "L")).toHaveAttribute("aria-checked", "true");
  await expect(radio("Text size", "M")).toBeDisabled();
  await expect(page.getByText("Presenter Mode sets L")).toBeVisible();
  await toggle("Presenter Mode").click();
  await expect(radio("Text size", "M")).toHaveAttribute("aria-checked", "true");
  await expect(radio("Text size", "S")).toBeEnabled();
  await toggle("Presenter Mode").click();
  await page.evaluate(() => { location.hash = "#/settings/connection"; });
  await expect(page.locator("[data-status]")).toContainText("KEY SET");
  await expect(page.locator("[data-status]")).not.toContainText("0001");
  await expect(page.getByRole("button", { name: "Show" })).toHaveCount(0);
});

test("Cost: every control saves and takes effect (mode, caps, warn, energy, estimates, confirm, HUD, spend)", async ({ page }) => {
  await open(page, "/settings/cost");
  await setKey(page);
  const mode = (n: string) => page.getByRole("radiogroup", { name: "Generation mode" }).getByRole("radio", { name: new RegExp(`^${n}`) });
  const radio = (group: string, name: string) => page.getByRole("radiogroup", { name: group }).getByRole("radio", { name, exact: true });
  const toggle = (name: string) => page.getByRole("switch", { name });
  const daily = page.getByLabel("Daily cap in US dollars");
  const creation = page.getByLabel("Creation cap in US dollars");

  // The mode cards' prices come from the price table (they said $0.20 / $0.40, about twice the real cost).
  await expect(mode("Lean")).toHaveAttribute("aria-checked", "true");
  await expect(mode("Lean")).toContainText("≈ $0.13 per character");
  await expect(mode("Standard")).toContainText("≈ $0.20 per character");
  await mode("Standard").click();
  await expect(mode("Standard")).toHaveAttribute("aria-checked", "true");

  await daily.fill("-1");
  await daily.press("Enter");
  await expect(page.getByText("Enter a positive number.")).toBeVisible();
  await daily.fill("2.5");
  await daily.press("Enter");
  await expect(page.getByText("Daily cap updated.")).toBeVisible();
  await creation.fill("0.8");
  await creation.press("Tab"); // commits on blur too
  await expect(page.getByText("Creation cap updated.")).toBeVisible();
  await radio("Warn at", "50 %").click();
  await radio("Default character energy", "2000 ⚡").click();
  await expect(radio("Default character energy", "2000 ⚡")).toHaveAttribute("aria-checked", "true");

  // Confirm before generating (on): the first generation asks with its estimate; Not now starts nothing.
  await page.evaluate(() => { location.hash = "#/w/wld_seedMeridian/c/chr_mockElena?tab=gallery"; });
  const gen = page.getByRole("button", { name: "Generate (≈ $0.02)" }).first();
  await gen.click();
  const ask = page.getByRole("dialog", { name: /Spend a little\?/ });
  await expect(ask).toContainText("≈$0.02");
  await ask.getByRole("button", { name: "Not now" }).click();
  await expect(ask).toBeHidden();

  // Cost HUD (on): a session header shows the running cost.
  const hud = page.getByText(/^\$[\d.]+ · [\d.]+k? tok$/);
  await page.evaluate(() => { location.hash = "#/w/wld_seedSunnyHollow/s/ses_seedHanaLongDay"; });
  await expect(hud).toBeVisible();

  // All three display toggles off; everything above survives a reload.
  await page.evaluate(() => { location.hash = "#/settings/cost"; });
  for (const name of ["Show cost estimates", "Confirm before generating", "Cost HUD"]) {
    await toggle(name).click();
    await expect(toggle(name)).toHaveAttribute("aria-checked", "false");
  }
  await page.reload();
  await expect(mode("Standard")).toHaveAttribute("aria-checked", "true");
  await expect(daily).toHaveValue("2.5");
  await expect(creation).toHaveValue("0.8");
  await expect(radio("Warn at", "50 %")).toHaveAttribute("aria-checked", "true");
  await expect(radio("Default character energy", "2000 ⚡")).toHaveAttribute("aria-checked", "true");
  for (const name of ["Show cost estimates", "Confirm before generating", "Cost HUD"]) await expect(toggle(name)).toHaveAttribute("aria-checked", "false");
  await radio("Cost view", "Spend").click();
  await expect(page.getByText(/of \$2\.50 daily cap/)).toBeVisible();

  // Estimates off: the buttons lose their "≈ $x" (the toggle used to change nothing). Confirm off: no dialog.
  await page.evaluate(() => { location.hash = "#/w/wld_seedMeridian/c/chr_mockElena?tab=gallery"; });
  const plain = page.getByRole("button", { name: "Generate", exact: true });
  await expect(plain.first()).toBeVisible();
  await expect(page.getByRole("button", { name: /≈/ })).toHaveCount(0); // (the energy panel's "≈ $x spent" is not a button)
  const before = await plain.count();
  await plain.first().click();
  await expect(plain).toHaveCount(before - 1); // that emotion is generating now
  await expect(ask).toHaveCount(0);

  // HUD off: the header has no cost.
  await page.evaluate(() => { location.hash = "#/w/wld_seedSunnyHollow/s/ses_seedHanaLongDay"; });
  await expect(page.getByRole("button", { name: "Readable", exact: true })).toBeVisible();
  await expect(hud).toHaveCount(0);
});

test("Data: Trim long pauses reaches replays; Reset keeps your own character; Delete all empties; both Resets bring the demo back", async ({ page }) => {
  // The wizard's portrait takes 20 s on the backend; on the CI runner the whole test passed 135 s (test.slow's 3 × 45 s,
  // 23 Oct) just before its last step, so it gets 4 minutes.
  test.setTimeout(240_000);
  const worldCard = (name: string) => page.getByRole("list", { name: "Worlds" }).getByRole("button", { name: new RegExp(`^${name}`) });
  const roster = page.getByRole("tabpanel", { name: /^Roster/ });
  const sarah = roster.getByRole("button", { name: /^Sarah, .*Open profile$/ });
  const trimRow = page.getByRole("switch", { name: "Trim long pauses in replays" });

  // Trim long pauses: off here, off in a replay's transport, and back on from the transport.
  await open(page, "/settings/data", { speed: 4 });
  await expect(trimRow).toHaveAttribute("aria-checked", "true");
  await trimRow.click();
  await expect(trimRow).toHaveAttribute("aria-checked", "false");
  await page.evaluate(() => { location.hash = "#/w/wld_seedSunnyHollow/s/ses_seedHanaLongDay"; });
  await page.getByRole("button", { name: "Replay", exact: true }).click();
  const trimGaps = page.getByRole("button", { name: "Trim gaps" });
  await expect(trimGaps).toHaveAttribute("aria-pressed", "false");
  await trimGaps.click();
  await expect(trimGaps).toHaveAttribute("aria-pressed", "true");
  await page.evaluate(() => { location.hash = "#/settings/data"; });
  await expect(trimRow).toHaveAttribute("aria-checked", "true");

  // A character of your own in a demo world (the wizard, as in wizard.spec.ts).
  await setKey(page);
  await page.evaluate(() => { location.hash = "#/w/wld_seedMeridian/create/seed"; });
  await page.getByRole("textbox", { name: "Seed line" }).fill("Sarah, a doctor");
  await page.getByRole("button", { name: /Draft with AI/ }).click();
  await expect(page.getByRole("heading", { name: "Make them yours" })).toBeVisible({ timeout: genTimeout(page) });
  await page.getByRole("button", { name: "Next: Look ▸" }).click();
  await page.getByRole("button", { name: /^Generate portrait/ }).click();
  await page.getByRole("dialog", { name: "Spend a little?" }).getByRole("button", { name: /^Generate ≈/ }).click();
  await expect(page.getByRole("heading", { name: "Pick a face" })).toBeVisible({ timeout: genTimeout(page) });
  await page.getByRole("button", { name: "Lock as base" }).click();
  await page.getByRole("button", { name: "Next: Emotions ▸" }).click();
  await page.getByRole("button", { name: "Skip for now" }).click();
  await page.getByRole("button", { name: "Next: Theme ▸" }).click();
  await page.getByRole("button", { name: "Next: Approve ▸" }).click();
  await page.getByRole("button", { name: "Approve & Summon ▸" }).click();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Sarah", level: 1 })).toBeVisible();

  // Reset demo data: the demo goes back to as shipped, and Sarah stays.
  await page.evaluate(() => { location.hash = "#/settings/data"; });
  await page.getByRole("button", { name: "Reset demo data" }).click();
  const resetAsk = page.getByRole("dialog", { name: "Reset demo data?" });
  await expect(resetAsk).toContainText("Worlds, characters and sessions you created stay");
  await resetAsk.getByRole("button", { name: "Reset demo data" }).click();
  await expect(page.getByText("Demo data restored.")).toBeVisible();
  await page.evaluate(() => { location.hash = "#/w/wld_seedMeridian"; });
  await expect(sarah).toBeVisible();
  await expect(roster.getByRole("button", { name: /^Amara Okafor, .*Open profile$/ })).toBeVisible();

  // Delete all data: Cancel deletes nothing; the button waits for the exact words; then no worlds and no key.
  const wipe = async () => {
    await page.evaluate(() => { location.hash = "#/settings/data"; });
    await page.getByRole("button", { name: "Delete all data…" }).click();
    const ask = page.getByRole("dialog", { name: "Delete all data?" });
    const go = ask.getByRole("button", { name: "Delete everything" });
    await expect(go).toBeDisabled();
    await ask.getByLabel("Type “DELETE ALL” to confirm").fill("DELETE AL");
    await expect(go).toBeDisabled();
    await ask.getByLabel("Type “DELETE ALL” to confirm").fill("delete all"); // any case (U-28)
    await go.click();
    await expect(page.getByText(/^All data deleted\./)).toBeVisible();
    await expect(page).toHaveURL(/#\/worlds$/);
    await expect(page.getByRole("button", { name: "Restore demo data" })).toBeVisible(); // the empty state
    await expect(worldCard("Meridian Council")).toHaveCount(0);
    await expect(page.getByText(/^Emotions \d+\/\d+$/)).toHaveCount(0); // no job left running for a deleted character
  };
  await page.evaluate(() => { location.hash = "#/settings/data"; });
  await page.getByRole("button", { name: "Delete all data…" }).click();
  await page.getByRole("dialog", { name: "Delete all data?" }).getByRole("button", { name: "Cancel" }).click();
  await page.evaluate(() => { location.hash = "#/worlds"; });
  await expect(worldCard("Meridian Council")).toBeVisible();
  await wipe();
  await page.evaluate(() => { location.hash = "#/settings/connection"; });
  await expect(page.locator("[data-status]")).toHaveAttribute("data-status", "missing");

  // Reset demo data after Delete all: both demo worlds are back; your own character went with the delete.
  await page.evaluate(() => { location.hash = "#/settings/data"; });
  await page.getByRole("button", { name: "Reset demo data" }).click();
  await page.getByRole("dialog", { name: "Reset demo data?" }).getByRole("button", { name: "Reset demo data" }).click();
  await expect(page.getByText("Demo data restored.")).toBeVisible();
  await page.evaluate(() => { location.hash = "#/worlds"; });
  await expect(worldCard("Meridian Council")).toBeVisible();
  await expect(worldCard("Sunny Hollow")).toBeVisible();
  await worldCard("Meridian Council").click();
  await expect(roster.getByRole("button", { name: /^Victor Hale, .*Open profile$/ })).toBeVisible();
  await expect(sarah).toHaveCount(0);

  // The empty Worlds screen's own "Restore demo data" does the same.
  await wipe();
  await page.getByRole("button", { name: "Restore demo data" }).click();
  await expect(worldCard("Meridian Council")).toBeVisible();
  await expect(worldCard("Sunny Hollow")).toBeVisible();
});
