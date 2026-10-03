#!/usr/bin/env node
// Horizon image-model test: base portrait (A1) + emotion edits (A2) for one character.
// See docs/ai/image-model-test/TESTING.md and README.md for the prompts and the scorecard.
//
// Usage (from the repo root):
//   node docs/ai/image-model-test/run.mjs --dry-run                 # print prompts, no API calls, no key needed
//   node docs/ai/image-model-test/run.mjs                           # Hana on Seedream 5.0 Flash, all 7 emotions
//   node docs/ai/image-model-test/run.mjs --emotions angry,embarrassed,blink
//   node docs/ai/image-model-test/run.mjs --model bytedance-seed/seedream-4.5
//   node docs/ai/image-model-test/run.mjs --base path/to/neutral.png   # reuse a base (e.g. hybrid test), edits only
//
// Options: --model  --emotions  --budget (USD, default 0.60)  --resolution (1K|2K)  --seed  --base  --dry-run
//
// Key: OPENROUTER_API_KEY from the environment, or docs/ai/image-model-test/.env (gitignored). The key is never printed.
// Output: docs/ai/image-model-test/output/<model>/<timestamp>/ with the images, run.json (provenance) and index.html.

import { mkdir, readFile, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { dirname, extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ENDPOINT = "https://openrouter.ai/api/v1/images";

// ---------- prompts (kept identical to TESTING.md) ----------

const STYLE =
  "Modern Japanese anime illustration, clean confident line art, soft cel shading with subtle gradients, " +
  "bright saturated but natural colours, expressive eyes with glossy highlights, fashionable contemporary " +
  "clothing with fabric detail, slice-of-life romantic-comedy aesthetic. Adult character with adult " +
  "proportions and a mature face.";

const APPEARANCE =
  "Hana Morisaki, a 26-year-old florist. Pink-tinted chestnut bob, green eyes, cherry-blossom hairpin. " +
  "Denim apron over a cream sundress. Sunny, affectionate vibe.";

const BASE_PROMPT = `${STYLE}

Subject: ${APPEARANCE}

Composition: single character, vertical 3:4 portrait, waist-up, centred, body turned slightly (three-quarter view) with face toward the viewer, eyes about one third from the top of the image, head and shoulders fully inside the frame with a little headroom, arms relaxed at the sides and hands out of frame.
Expression: calm neutral, mouth closed, attentive eyes looking at the viewer.
Background: plain seamless flat light warm-grey studio background, no scenery, no props, no cast shadow.
Lighting: soft even front key light with a gentle rim light.

Avoid: text, letters, logos, watermark, signature, border, frame, extra people, visible hands, cropped head, childlike or teenage features, photorealism, 3D render look.`;

const EMOTIONS = {
  happy: "a warm open smile showing a little of the upper teeth, eyes softly crinkled",
  sad: "inner brows raised, eyes lowered and slightly glossy, mouth gently downturned",
  angry: "brows drawn down and together, narrowed eyes, tight mouth, faint flush on the cheeks",
  surprised: 'eyebrows high, eyes wide open, mouth in a small open "o"',
  thinking: "eyes glancing up and to the side, one eyebrow raised, lips pursed slightly to one side",
  embarrassed: "a blush across the cheeks and nose, an awkward small smile, eyes glancing away",
  blink: "eyes fully closed and relaxed, otherwise identical to the original",
};

const editPrompt = (emotion) =>
  "Edit this image. Keep the exact same character: identical face shape, eye colour, hairstyle, hair colour, " +
  "skin tone, outfit, accessories, pose, framing, camera angle, lighting, background and art style. " +
  `Change ONLY the facial expression to: ${emotion}.\n` +
  "Do not add hands, props, text, tears streaming, or any new objects. Do not change the crop.";

// ---------- args, key ----------

function parseArgs(argv) {
  const out = { model: "bytedance-seed/seedream-5-0-flash", budget: 0.6, resolution: "1K", emotions: Object.keys(EMOTIONS) };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => {
      const v = argv[++i];
      if (v === undefined) fail(`${a} needs a value`);
      return v;
    };
    if (a === "--dry-run") out.dryRun = true;
    else if (a === "--model") out.model = next();
    else if (a === "--budget") out.budget = Number(next());
    else if (a === "--resolution") out.resolution = next();
    else if (a === "--seed") out.seed = Number(next());
    else if (a === "--base") out.base = next();
    else if (a === "--emotions") out.emotions = next().split(",").map((s) => s.trim()).filter(Boolean);
    else fail(`unknown option ${a}`);
  }
  const unknown = out.emotions.filter((e) => !(e in EMOTIONS));
  if (unknown.length) fail(`unknown emotion(s): ${unknown.join(", ")}. Valid: ${Object.keys(EMOTIONS).join(", ")}`);
  if (!(out.budget > 0)) fail("--budget must be a positive number");
  return out;
}

async function loadKey() {
  if (process.env.OPENROUTER_API_KEY) return process.env.OPENROUTER_API_KEY.trim();
  const envFile = join(HERE, ".env");
  if (existsSync(envFile)) {
    const m = (await readFile(envFile, "utf8")).match(/^\s*OPENROUTER_API_KEY\s*=\s*"?([^"\r\n]+)"?\s*$/m);
    if (m) return m[1].trim();
  }
  fail("OPENROUTER_API_KEY not set. Put it in docs/ai/image-model-test/.env (see .env.example) or the environment.");
}

function fail(msg) {
  console.error(`✖ ${msg}`);
  process.exit(1);
}

// ---------- API ----------

const EXT = { "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp" };
const MIME = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp" };

async function generate(key, body) {
  for (let attempt = 1; ; attempt++) {
    const t0 = Date.now();
    let res;
    try {
      res = await fetch(ENDPOINT, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${key}`,
          "Content-Type": "application/json",
          "X-Title": "Horizon image-model test",
        },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(180_000),
      });
    } catch (err) {
      if (attempt < 2) { await sleep(3000); continue; }
      throw new Error(`network error: ${err.message}`);
    }
    const ms = Date.now() - t0;
    const text = await res.text();
    let json;
    try { json = JSON.parse(text); } catch { json = null; }
    if (!res.ok) {
      const msg = json?.error?.message ?? text.slice(0, 300);
      if ((res.status === 429 || res.status >= 500) && attempt < 2) {
        console.warn(`  ! HTTP ${res.status} (${msg}), retrying once…`);
        await sleep(5000);
        continue;
      }
      throw new Error(`HTTP ${res.status}: ${msg}`);
    }
    const img = json?.data?.[0];
    if (!img?.b64_json) throw new Error(`no image in response: ${text.slice(0, 300)}`);
    return { bytes: Buffer.from(img.b64_json, "base64"), mediaType: img.media_type ?? "image/png", cost: json.usage?.cost, ms };
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------- run ----------

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const jobs = [];
  if (!opts.base) jobs.push({ name: "neutral", prompt: BASE_PROMPT });
  for (const e of opts.emotions) jobs.push({ name: e, prompt: editPrompt(EMOTIONS[e]), edit: true });

  if (opts.dryRun) {
    for (const j of jobs) console.log(`\n=== ${j.name}${j.edit ? " (edit, reference = base)" : ""} ===\n${j.prompt}`);
    console.log(`\n${jobs.length} call(s) on ${opts.model}, budget $${opts.budget.toFixed(2)}. Dry run: nothing sent.`);
    return;
  }

  const key = await loadKey();
  const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  const outDir = join(HERE, "output", opts.model.replace(/[^a-z0-9.-]+/gi, "_"), stamp);
  await mkdir(outDir, { recursive: true });

  const run = { model: opts.model, resolution: opts.resolution, aspectRatio: "3:4", seed: opts.seed ?? null, character: APPEARANCE, startedAt: new Date().toISOString(), budget: opts.budget, results: [] };
  let spent = 0;
  let lastCost = 0.05; // conservative guess until the first real cost arrives

  let baseDataUrl = null;
  if (opts.base) {
    const ext = extname(opts.base).toLowerCase();
    if (!MIME[ext]) fail(`--base must be .png, .jpg or .webp`);
    baseDataUrl = `data:${MIME[ext]};base64,${(await readFile(opts.base)).toString("base64")}`;
    run.base = opts.base;
  }

  console.log(`Model ${opts.model} · ${jobs.length} call(s) · budget $${opts.budget.toFixed(2)}\nOutput ${relative(process.cwd(), outDir)}\n`);

  for (const job of jobs) {
    if (spent + lastCost > opts.budget) {
      console.warn(`■ Budget stop: spent $${spent.toFixed(4)}, next call ≈ $${lastCost.toFixed(4)} would exceed $${opts.budget.toFixed(2)}.`);
      run.stoppedByBudget = true;
      break;
    }
    if (job.edit && !baseDataUrl) {
      console.warn(`■ Skipping ${job.name}: no base image.`);
      run.results.push({ name: job.name, error: "no base image" });
      continue;
    }
    const body = { model: opts.model, prompt: job.prompt, resolution: opts.resolution, aspect_ratio: "3:4", n: 1 };
    if (opts.seed !== undefined) body.seed = opts.seed;
    if (job.edit) body.input_references = [{ type: "image_url", image_url: { url: baseDataUrl } }];

    process.stdout.write(`→ ${job.name.padEnd(12)}`);
    try {
      const r = await generate(key, body);
      const file = `${String(run.results.length).padStart(2, "0")}-${job.name}${EXT[r.mediaType] ?? ".png"}`;
      await writeFile(join(outDir, file), r.bytes);
      const cost = typeof r.cost === "number" ? r.cost : null;
      spent += cost ?? lastCost;
      if (cost !== null) lastCost = cost;
      if (!job.edit) baseDataUrl = `data:${r.mediaType};base64,${r.bytes.toString("base64")}`;
      run.results.push({ name: job.name, file, prompt: job.prompt, edit: !!job.edit, cost, ms: r.ms, kb: Math.round(r.bytes.length / 1024) });
      console.log(`✓ ${file}  ${(r.ms / 1000).toFixed(1)}s  ${cost === null ? "cost n/a" : `$${cost.toFixed(4)}`}`);
    } catch (err) {
      run.results.push({ name: job.name, prompt: job.prompt, edit: !!job.edit, error: err.message });
      console.log(`✖ ${err.message}`);
    }
  }

  run.spent = Number(spent.toFixed(4));
  run.finishedAt = new Date().toISOString();
  await writeFile(join(outDir, "run.json"), JSON.stringify(run, null, 2));
  await writeFile(join(outDir, "index.html"), contactSheet(run));
  console.log(`\nSpent $${spent.toFixed(4)} of $${opts.budget.toFixed(2)}. Open ${relative(process.cwd(), join(outDir, "index.html"))} to compare.`);
}

function contactSheet(run) {
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const cells = run.results.map((r) => r.file
    ? `<figure><img src="${esc(r.file)}" alt="${esc(r.name)}"><figcaption><b>${esc(r.name)}</b> · ${(r.ms / 1000).toFixed(1)}s · ${r.cost == null ? "n/a" : "$" + r.cost.toFixed(4)} · ${r.kb} KB</figcaption></figure>`
    : `<figure class="err"><div>${esc(r.error)}</div><figcaption><b>${esc(r.name)}</b> · failed</figcaption></figure>`).join("\n");
  return `<!doctype html><meta charset="utf-8"><title>${esc(run.model)} · Hana</title>
<style>body{margin:0;padding:24px;background:#0b0b0f;color:#f5f2ea;font:14px/1.5 system-ui,sans-serif}
h1{font-size:18px;margin:0 0 4px}p{margin:0 0 20px;color:#a9a59c}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px}
figure{margin:0}img{width:100%;aspect-ratio:3/4;object-fit:cover;border-radius:6px;background:#1a1a20}
.err div{aspect-ratio:3/4;display:grid;place-items:center;padding:12px;border:1px dashed #e5484d;border-radius:6px;color:#e5484d}
figcaption{margin-top:6px;color:#a9a59c}b{color:#f5f2ea}</style>
<h1>${esc(run.model)} · ${esc(run.resolution)} · 3:4</h1>
<p>${esc(run.character)}<br>Spent $${run.spent.toFixed(4)} of $${run.budget.toFixed(2)}${run.stoppedByBudget ? " · stopped by budget" : ""} · ${esc(run.startedAt)}</p>
<div class="grid">
${cells}
</div>`;
}

main().catch((err) => fail(err.stack ?? err.message));
