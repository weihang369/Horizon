// The persona-prompt twin against the backend's shared fixtures (docs/ai/04 P10; persona-prompt "The preview is the
// real prompt"): every case in backend/tests/fixtures/persona_prompt/ must come out byte for byte. Owner: AI.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { compilePersona, cutTo, debateCue, moodLine, PROMPT_VERSION, safetyCueLines, turnCueSentence, type PersonaInput, type PersonaPrompt } from "./personaPrompt";
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
    expect(PROMPT_VERSION).toBe("agent-9");
  });
});

// Doc 07 G3 (group-watch D10; persona-prompt "Same table in both languages"): the same cases as persona.py's
// turn_cue_sentence().
interface CueCase { cue: string | null; answered: string | null; user?: string | null; sentence: string | null }
const CUE = JSON.parse(readFileSync(path.resolve(__dirname, "../../../backend/tests/fixtures/turn_cue/cases.json"), "utf8")) as { cases: CueCase[] };

describe("turnCueSentence (shared with persona.py's turn_cue_sentence)", () => {
  for (const c of CUE.cases) {
    it(`${c.cue ?? "none"} ${c.answered ?? ""} ${c.user ?? ""}`, () => {
      expect(turnCueSentence(c.cue, c.answered, c.user)).toBe(c.sentence);
    });
  }
});

// M11 (debate D10): doc 08 V4's debate cue table, shared with persona.py's debate_cue().
interface DebateCueCase { phase: string; panel: boolean; extended: boolean; teammates: string[]; afterInterject: boolean; cue: string | null }
const DEBATE = JSON.parse(readFileSync(path.resolve(__dirname, "../../../backend/tests/fixtures/debate_cue/cases.json"), "utf8")) as { cases: DebateCueCase[] };

describe("debateCue (shared with persona.py's debate_cue)", () => {
  for (const c of DEBATE.cases) {
    it(`${c.phase}${c.panel ? " panel" : ""}${c.extended ? " extended" : ""} ${c.teammates.join("+")}${c.afterInterject ? " interject" : ""}`, () => {
      expect(debateCue(c.phase, { panel: c.panel, extended: c.extended, teammates: c.teammates, afterInterject: c.afterInterject })).toBe(c.cue);
    });
  }
});

// M14 (safety D6): doc 11 S3, S4's cue lines, shared with persona.py's safety_cue_lines().
interface SafetyCueCase { steer: boolean; care: boolean; wording: "chat" | "debate" | "scene"; lines: string[] }
const SAFETY = JSON.parse(readFileSync(path.resolve(__dirname, "../../../backend/tests/fixtures/safety_cue/cases.json"), "utf8")) as { cases: SafetyCueCase[] };

describe("safetyCueLines (shared with persona.py's safety_cue_lines)", () => {
  for (const c of SAFETY.cases) {
    it(`steer ${c.steer} care ${c.care} ${c.wording}`, () => {
      expect(safetyCueLines(c.steer, c.care, c.wording)).toEqual(c.lines);
    });
  }
});
