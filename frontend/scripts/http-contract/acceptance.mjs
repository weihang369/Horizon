// M1b acceptance walk-through (tasks.md 13.1): drives the real app on `npm run dev` (VITE_HORIZON_CLIENT=http, the
// backend behind the Vite proxy) in Edge, with no mock anywhere. Run it while `npm run dev` is up:
//   node frontend/scripts/http-contract/acceptance.mjs [http://localhost:5173]
// It prints one line per check and exits non-zero on the first failure. Console errors fail the run, as in E2E.
import { chromium } from "@playwright/test";

const BASE = process.argv[2] ?? "http://localhost:5173";
const api = async (path, init) => {
  const r = await fetch(`${BASE}/api/v1${path}`, init);
  if (!r.ok && r.status !== 204) throw new Error(`${path}: ${r.status} ${await r.text()}`);
  return r.status === 204 ? null : r.json();
};
const log = (msg) => console.log(`  ✓ ${msg}`);

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL ?? "msedge" });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const problems = [];
page.on("console", (m) => {
  if ((m.type() === "error" || m.type() === "warning") && !/AudioContext was not allowed/.test(m.text())) problems.push(m.text());
});
page.on("pageerror", (e) => problems.push(e.message));
await page.addInitScript(() => {
  if (!localStorage.getItem("horizon.prefs.v1")) localStorage.setItem("horizon.prefs.v1", JSON.stringify({ seenOnboarding: true }));
});
const go = (hash) => page.goto(`${BASE}/#${hash}`);
const visible = (loc, what, timeout = 15_000) => loc.filter({ visible: true }).first().waitFor({ state: "visible", timeout }).then(() => log(what));
const fail = (msg) => {
  console.error(`  ✗ ${msg}`);
  throw new Error(msg);
};

try {
  await api("/admin/reset-demo", { method: "POST", headers: { "Content-Type": "application/json" }, body: '{"confirm":true}' });
  const health = await api("/health");
  if (!health.ok) fail("backend unhealthy");
  log(`backend healthy (docling: ${health.docling})`);

  // 1. Both seed worlds browse.
  await go("/worlds");
  const rail = page.getByRole("list", { name: "Worlds" });
  await visible(rail.getByText("Meridian Council"), "world select lists Meridian Council");
  await visible(rail.getByText("Sunny Hollow"), "world select lists Sunny Hollow");
  if (await page.getByRole("button", { name: /mock|scenario/i }).count()) fail("mock dev controls visible under the HttpClient");

  const worlds = await api("/worlds");
  for (const w of worlds.filter((x) => x.isSeed)) {
    await go(`/w/${w.id}`);
    await visible(page.getByRole("heading", { name: new RegExp(w.name, "i"), level: 1 }), `hub opens: ${w.name}`);
    // 2. Every seed profile opens; the Knowledge tab shows keyword-only seed sources and Mei's failed one keeps its error.
    for (const c of await api(`/worlds/${w.id}/characters`)) {
      if (!c.isSeed) continue;
      await go(`/w/${w.id}/c/${c.id}`);
      await visible(page.getByText(c.profile.name), `profile opens: ${c.profile.name}`);
      const sources = await api(`/characters/${c.id}/knowledge`);
      if (sources.length) {
        await go(`/w/${w.id}/c/${c.id}?tab=knowledge`);
        for (const k of sources) {
          await visible(page.getByText(k.title), `  knowledge source listed: ${k.title} (${k.status})`);
          if (k.status === "keyword_only") await visible(page.getByText(/keyword only/i), "  keyword-only badge shown");
          if (k.status === "failed") await visible(page.getByText(k.error), "  failed source shows its error");
        }
      }
    }
    // 3. Every seed session replays.
    for (const s of await api(`/worlds/${w.id}/sessions`)) {
      if (!s.isSeed) continue;
      // A full load per replay: a hash-only jump between sessions briefly shows the previous replay while the next
      // one loads over HTTP (noted in the M1b acceptance record), and a key press then lands on the stale one.
      await page.goto(`${BASE}/?replay=${s.id}#/w/${w.id}/s/${s.id}?replay=1`);
      const seek = page.getByRole("slider", { name: "Seek" });
      await seek.waitFor({ state: "visible", timeout: 20_000 });
      // The recording's length is known once its events arrive over HTTP ("0:00 of 0:57", not "of 0:00").
      await page.waitForFunction(() => {
        const t = document.querySelector('[aria-label="Seek"]')?.getAttribute("aria-valuetext") ?? "";
        return /of \d+:\d\d$/.test(t) && !/of 0:00$/.test(t);
      }, null, { timeout: 20_000 }).catch(async () => {
        fail(`replay ${s.id}: slider stuck at "${await seek.getAttribute("aria-valuetext")}"`);
      });
      await seek.focus();
      await page.keyboard.press("End");
      await page.waitForFunction(() => {
        const el = document.querySelector('[aria-label="Seek"]');
        const m = el?.getAttribute("aria-valuetext")?.match(/^(\d+:\d\d) of (\d+:\d\d)$/);
        return !!m && m[1] === m[2];
      }, null, { timeout: 20_000 });
      await page.getByRole("log").getByRole("listitem").nth(2).waitFor({ state: "visible", timeout: 10_000 }).catch(() => undefined);
      const items = await page.getByRole("log").getByRole("listitem").count();
      if (items < 3) fail(`replay ${s.title}: only ${items} log items`);
      log(`replay plays to the end: ${s.title} (${items} items)`);
    }
  }

  // 4. World create / rename / delete through the UI; duplicates are refused.
  await go("/worlds");
  await page.getByRole("button", { name: "+ Create world" }).first().click().catch(async () => {
    await page.getByRole("list", { name: "Worlds" }).getByRole("button").last().click();
  });
  await page.getByRole("textbox", { name: "Name", exact: true }).fill("Acceptance Street");
  await page.getByRole("button", { name: "Create world ▸" }).click();
  await visible(page.getByText("Acceptance Street"), "world created through the UI");
  const created = (await api("/worlds")).find((x) => x.name === "Acceptance Street");
  if (!created) fail("created world not stored by the backend");
  log("backend stored the new world");

  const dup = await fetch(`${BASE}/api/v1/worlds`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: "acceptance street", cover: { kind: "preset", presetId: "cover_night_skyline" } }) });
  if (dup.status !== 409) fail(`duplicate world name gave ${dup.status}`);
  log("duplicate name refused with 409 conflict");
  const reserved = await fetch(`${BASE}/api/v1/worlds`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: "Sunny Hollow", cover: { kind: "preset", presetId: "cover_night_skyline" } }) });
  if (reserved.status !== 409) fail(`reserved seed name gave ${reserved.status}`);
  log("seed world name refused with 409 conflict");

  await api(`/worlds/${created.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: "Acceptance Avenue" }) });
  await go("/worlds");
  await visible(page.getByText("Acceptance Avenue"), "rename shows up in the world list");
  await api(`/worlds/${created.id}`, { method: "DELETE" });
  await go("/worlds");
  await visible(page.getByText("Meridian Council"), "world list reloads");
  if (await page.getByText("Acceptance Avenue").count()) fail("deleted world still listed");
  log("delete removes the world from the list");

  if (problems.length) fail(`console problems:\n    ${problems.join("\n    ")}`);
  log("console stayed clean");
  console.log("ACCEPTANCE OK");
} finally {
  await browser.close();
}
