// Shared chunker fixtures (backend/tests/fixtures/chunker/*.json): the mock's `pack@2` twin must give the backend's
// pieces case for case (rag design D3; demo-data "The MockClient chunks like the backend"). Paged fixtures need page
// markers read as pages, which only the backend does (the mock has no PDFs): the backend's tests cover them, and this
// file checks that they are the only fixtures the twin leaves out.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { CHUNKER_VERSION, countTokens, MAX, pack } from "./chunker";
import { paragraphs } from "./knowledge";

interface Fixture { what: string; paged: boolean; markdown: string; pieces: { text: string; locator: string; heading: string | null }[] }
const DIR = path.resolve(__dirname, "../../../../backend/tests/fixtures/chunker");
const files = readdirSync(DIR).filter((f) => f.endsWith(".json")).sort();
const load = (f: string) => JSON.parse(readFileSync(path.join(DIR, f), "utf8")) as Fixture;
const paged = files.filter((f) => load(f).paged);
const shared = files.filter((f) => !load(f).paged);

describe("pack@2 twin", () => {
  it("reads the shared fixture set; only the paged (PDF) fixtures are backend-only", () => {
    expect(files.length).toBeGreaterThanOrEqual(11);
    expect(CHUNKER_VERSION).toBe("pack@2");
    for (const f of paged) expect(load(f).markdown).toMatch(/<!-- page \d+ -->/);   // why they are backend-only
  });

  for (const f of shared) {
    const fx = load(f);
    it(`${f}: ${fx.what}`, () => {
      expect(pack(fx.markdown)).toEqual(fx.pieces);
      for (const p of pack(fx.markdown)) expect(countTokens(p.text)).toBeLessThanOrEqual(MAX);
    });
  }

  it("paragraphs() hands the pipeline the pieces and their locators", () => {
    expect(paragraphs("# Soups\n\nMiso first.\n\nThen tofu.")).toEqual({
      chunks: ["# Soups\n\nMiso first.\n\nThen tofu."], locators: ["§ Soups"], locator: "¶",
    });
  });
});
