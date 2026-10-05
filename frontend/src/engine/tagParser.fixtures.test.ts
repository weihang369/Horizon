// Shared inline-emotion-tag fixtures (backend/tests/fixtures/tag_parser/*.json, session-runtime design D11): a
// test-only TS reference parser runs the same cases as the backend's naive engine parser, so the rules are
// language-neutral. Owner: SWE.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { EMOTIONS } from "../contract/types";

interface TagCase {
  name: string; doc: string; chunks: string[]; previous: string;
  expected: { emotion: string; source: "llm" | "default"; text: string };
}
const DIR = path.resolve(__dirname, "../../../backend/tests/fixtures/tag_parser");
const cases = readdirSync(DIR).filter((f) => f.endsWith(".json")).sort()
  .map((f) => JSON.parse(readFileSync(path.join(DIR, f), "utf8")) as TagCase);

const MAX_HEAD = 32;
const TAG = /<e:[^<>]{0,30}>/g;
const PARTIAL = /<(?:e(?::[^<>]{0,30})?)?$/;

/** Reference parser: the rules of doc backend/05 §5, written independently of the Python one. */
function parse(chunks: string[], previous: string): { emotion: string; source: string; text: string } {
  const labels = EMOTIONS as readonly string[];
  let head = "";
  let decided: { emotion: string; source: string } | null = null;
  let carry = "";
  let text = "";
  let lead = false;
  const body = (chunk: string) => {
    let t = (carry + chunk).replace(TAG, "");
    carry = "";
    if (lead) {
      t = t.trimStart();
      lead = !t;
    }
    const m = PARTIAL.exec(t);
    if (m && t.length - m.index <= MAX_HEAD) {
      carry = t.slice(m.index);
      t = t.slice(0, m.index);
    }
    text += t;
  };
  const release = (label: string | null, rest: string) => {
    decided = label ? { emotion: label, source: "llm" } : { emotion: previous, source: "default" };
    head = "";
    body(rest);
  };
  for (const c of chunks) {
    if (decided) { body(c); continue; }
    head += c;
    const s = head.trimStart();
    if (!s) continue;
    if (!("<e:".startsWith(s) || s.startsWith("<e:"))) { release(null, head); continue; }
    if (s.startsWith("<e:") && s.includes(">")) {
      const end = s.indexOf(">");
      const label = s.slice(3, end);
      lead = true;
      release(labels.includes(label) ? label : null, s.slice(end + 1));
      continue;
    }
    if (head.length >= MAX_HEAD) release(null, head);
  }
  if (!decided) {
    decided = { emotion: previous, source: "default" };
    text += head.replace(TAG, "");
  }
  text += carry;
  return { ...(decided as { emotion: string; source: string }), text };
}

describe("emotion tag fixtures (shared with the backend's naive engine)", () => {
  it("found the cases", () => {
    expect(cases.length).toBeGreaterThanOrEqual(6);
  });
  for (const c of cases) {
    it(c.name, () => {
      expect(parse(c.chunks, c.previous)).toEqual(c.expected);
    });
  }
});
