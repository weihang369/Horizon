// The persona-prompt twin against the backend's shared fixtures (docs/ai/04 P10; persona-prompt "The preview is the
// real prompt"): every case in backend/tests/fixtures/persona_prompt/ must come out byte for byte. Owner: AI.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { compilePersona, cutTo, moodLine, PROMPT_VERSION, type PersonaInput, type PersonaPrompt } from "./personaPrompt";
import { countTokens } from "./tokens";

interface Fixture { name: string; doc: string; input: PersonaInput; expected: PersonaPrompt }
const DIR = path.resolve(__dirname, "../../../backend/tests/fixtures/persona_prompt");
const cases = readdirSync(DIR).filter((f) => f.endsWith(".json")).sort()
  .map((f) => JSON.parse(readFileSync(path.join(DIR, f), "utf8")) as Fixture);

describe("persona prompt fixtures (shared with the backend's agent compiler)", () => {
  it("found the cases", () => {
    expect(cases.length).toBeGreaterThanOrEqual(11);
  });
  for (const c of cases) {
    it(c.name, () => {
      expect(compilePersona(c.input)).toEqual(c.expected);
    });
  }
});

describe("countTokens and cutTo", () => {
  it("counts UTF-8 bytes / 3, rounded up", () => {
    expect([countTokens(""), countTokens("abc"), countTokens("abcd"), countTokens("我"), countTokens("😀")]).toEqual([0, 1, 2, 1, 2]);
  });
  it("never splits a surrogate pair", () => {
    expect(cutTo("😀".repeat(100), 10)).toEqual(["😀".repeat(6) + "…", true]);
  });
  it("skips an abbreviation", () => {
    expect(cutTo("She trained early. Then she met Dr. Kim and stayed for years and years and years.", 12))
      .toEqual(["She trained early.…", true]);
  });
});

// docs/ai/06 E4 (turn-plan-emotion D16; persona-prompt "Phrase per face"): the same cases as persona.py's mood_line().
interface MoodCase { face: string; manual: boolean; line: string | null }
const MOOD = JSON.parse(readFileSync(path.resolve(__dirname, "../../../backend/tests/fixtures/mood_line/cases.json"), "utf8")) as { cases: MoodCase[] };

describe("moodLine (shared with persona.py's mood_line)", () => {
  for (const c of MOOD.cases) {
    it(`${c.face} ${c.manual ? "manual" : "auto"}`, () => {
      expect(moodLine(c.face, c.manual)).toBe(c.line);
    });
  }
  it("names the agent-1 prompt (the mood line is off by default, D40)", () => {
    expect(PROMPT_VERSION).toBe("agent-1");
  });
});
