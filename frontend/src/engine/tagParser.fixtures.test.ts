// Shared inline-emotion-tag fixtures (backend/tests/fixtures/tag_parser/*.json, session-runtime design D11): a
// test-only TS reference parser runs the same cases as the backend's naive engine parser, so the rules are
// language-neutral.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { EMOTIONS } from "../contract/types";

interface TagCase {
  name: string; doc: string; chunks: string[]; previous: string;
  /** docs/ai/03 C6: the speaker's own name, stripped from the start of the first line (before or after the tag). */
  speaker?: string;
  /** docs/ai/04 P6: strip at every line start (the agent path, M8). The naive path is first line only (false). */
  perLine?: boolean;
  expected: { emotion: string; source: "llm" | "default"; text: string };
}
const DIR = path.resolve(__dirname, "../../../backend/tests/fixtures/tag_parser");
const cases = readdirSync(DIR).filter((f) => f.endsWith(".json")).sort()
  .map((f) => JSON.parse(readFileSync(path.join(DIR, f), "utf8")) as TagCase);

const MAX_HEAD = 32;
const TAG = /<\/?e:[^<>]{0,30}>/g;   // a closing </e:…> too (M11 debate D31.3)
const PARTIAL = /<\/?(?:e(?::[^<>]{0,30})?)?$/;

const escapeRe = (x: string) => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** C6 on the whole stream: a leading "<name>:" (any case, spaces around the colon) before or after the tag goes.
 *  Per line (doc 04 P6, the agent path): the same prefix also goes at the start of every later line. */
function parseNamed(chunks: string[], previous: string, speaker?: string, perLine = false): { emotion: string; source: string; text: string } {
  if (!speaker) return parse(chunks, previous);
  const prefix = new RegExp(`^\\s*${escapeRe(speaker)}[ \\t]*:[ \\t]*`, "i");
  const joined = chunks.join("");
  const before = prefix.exec(joined);
  const out = parse(before ? [joined.slice(before[0].length)] : chunks, previous);
  const after = out.source === "llm" ? prefix.exec(out.text) : null;
  const named = after ? { ...out, text: out.text.slice(after[0].length) } : out;
  if (!perLine) return named;
  const line = new RegExp(`^[ \\t]*${escapeRe(speaker)}[ \\t]*:[ \\t]*`, "i");
  return { ...named, text: named.text.split("\n").map((l, i) => (i === 0 ? l : l.replace(line, ""))).join("\n") };
}

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
    // D37: a bare "<label>" (one of the 7, any case) at the head counts as the tag
    const low = s.toLowerCase();
    const bare = labels.find((l) => low.startsWith(`<${l}>`));
    if (bare) { lead = true; release(bare, s.slice(bare.length + 2)); continue; }
    if (labels.some((l) => `<${l}>`.startsWith(low)) && head.length < MAX_HEAD) continue;
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
      expect(parseNamed(c.chunks, c.previous, c.speaker, c.perLine)).toEqual(c.expected);
    });
  }
});
