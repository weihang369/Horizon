import { describe, expect, it } from "vitest";
import { BEGIN, checkAssets, END, globToRegExp } from "./check";
import type { Inventory } from "./check";

const inv: Inventory = {
  files: ["seed/assets/placeholder/portraits/chr_a/neutral.svg", "seed/assets/placeholder/portraits/chr_b/happy.svg", "frontend/public/og.jpg"],
  fonts: ["@fontsource/anton"],
  tracks: { trk_main: "CC0-1.0" },
};
const HEAD = "| Pattern | Kind | Source | Credit / provenance | Licence |\n|---|---|---|---|---|";
const md = (...rows: string[]) => `# Assets\n\nProse.\n\n${BEGIN}\n${HEAD}\n${rows.join("\n")}\n${END}\n`;
const COMPLETE = [
  "| `seed/assets/placeholder/portraits/**` | Placeholder portraits | procedural | Horizon seed build | MIT |",
  "| `frontend/public/og.jpg` | Social card | procedural | Screenshot of the app | MIT |",
  "| `npm:@fontsource/anton` | Font | font | Anton by Vernon Adams, via Fontsource | OFL-1.1 |",
  "| `track:trk_main` | System track | procedural | Procedural sketch | CC0-1.0 |",
];

describe("assets:check (asset-credits spec, D16)", () => {
  it("passes a complete table and counts what it checked", () => {
    expect(checkAssets(inv, md(...COMPLETE))).toEqual({ problems: [], assets: 5, rows: 4 });
  });

  it("fails on a shipped file that no row covers, and names it", () => {
    const r = checkAssets({ ...inv, files: [...inv.files, "frontend/public/new.png"] }, md(...COMPLETE));
    expect(r.problems).toEqual(["no ASSETS.md row covers frontend/public/new.png"]);
  });

  it("fails on a stale row that matches nothing", () => {
    const r = checkAssets(inv, md(...COMPLETE, "| `frontend/public/gone.svg` | Old | procedural | Removed | MIT |"));
    expect(r.problems).toEqual([expect.stringMatching(/line \d+ \(frontend\/public\/gone\.svg\): matches no shipped asset/)]);
  });

  it("fails on an ai row without its model, and names the field", () => {
    const ai = "| `frontend/public/og.jpg` | Social card | ai | date=2026-10-01; prompt=docs/x.md; technique=base | MIT |";
    const r = checkAssets(inv, md(...COMPLETE.slice(0, 1), ai, ...COMPLETE.slice(2)));
    expect(r.problems).toEqual([expect.stringMatching(/an ai row needs model=/)]);
  });

  it("accepts an ai row with model, date, prompt and technique", () => {
    const ai = "| `frontend/public/og.jpg` | Social card | ai | model=bytedance-seed/seedream-5-0-flash; date=2026-10-01; prompt=docs/x.md; technique=base | MIT |";
    expect(checkAssets(inv, md(COMPLETE[0], ai, ...COMPLETE.slice(2))).problems).toEqual([]);
  });

  it("fails on an unknown licence identifier and an unknown source", () => {
    const r = checkAssets(inv, md(COMPLETE[0], "| `frontend/public/og.jpg` | Social card | stock | Somewhere | Public Domain |", ...COMPLETE.slice(2)));
    expect(r.problems).toEqual([
      expect.stringMatching(/source must be one of/),
      expect.stringMatching(/"Public Domain" is not a known SPDX licence identifier/),
    ]);
  });

  it("fails when a track's licence disagrees with seed/system-tracks.json", () => {
    const r = checkAssets(inv, md(...COMPLETE.slice(0, 3), "| `track:trk_main` | System track | procedural | Procedural sketch | CC-BY-4.0 |"));
    expect(r.problems).toEqual([expect.stringMatching(/licence CC-BY-4\.0 disagrees with seed\/system-tracks\.json \(CC0-1\.0\)/)]);
  });

  it("needs the markers", () => {
    expect(() => checkAssets(inv, "# Assets\n")).toThrow(/assets:begin/);
  });

  it("globs: ** spans directories, * stays in one segment", () => {
    expect(globToRegExp("seed/assets/**").test("seed/assets/a/b/c.svg")).toBe(true);
    expect(globToRegExp("frontend/public/*.svg").test("frontend/public/favicon.svg")).toBe(true);
    expect(globToRegExp("frontend/public/*.svg").test("frontend/public/x/favicon.svg")).toBe(false);
  });
});
