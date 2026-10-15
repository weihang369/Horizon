// `pack@2` in the mock (doc 10 K1; rag design D3): the twin of backend/horizon/ai/chunker.py on Markdown and text.
// The mock has no pages and no Docling, so page markers only end a block here. Both sides read the shared fixtures in
// backend/tests/fixtures/chunker/ (chunker.test.ts), so a rule changed on one side fails the other's tests.
//
// - Blocks: headings (one line), paragraphs (whitespace collapsed), lists and tables (each line collapsed, line breaks
//   kept), split on blank lines and page markers.
// - A heading is carried to the top of the next piece, never a piece of its own; a piece never crosses a heading change.
// - Blocks are packed, joined by a blank line, until a piece reaches 300 tokens or the next block would pass 400.
// - A block too large for an empty piece is cut at the sentence end nearest 300 that fits (a line, for lists and
//   tables, each later table part repeating the header row unless the header and its first row don't fit one piece
//   together), else at the last word that fits.
// - Tokens are UTF-8 bytes / 3, rounded up (the backend's `count_tokens`).
// - Locators: `§ {nearest heading}`, else `¶ {n}`; `heading` is the heading path joined with " › ".

export const CHUNKER_VERSION = "pack@2";
export const TARGET = 300;
export const MAX = 400;

export interface Piece { text: string; locator: string; heading: string | null }

type Kind = "heading" | "para" | "list" | "table";
interface Part { kind: Kind; text: string; header: number; repeated?: number }   // repeated: a leading repeated header

const PAGE = /^\s*<!--\s*page\s+(\d+)\s*-->\s*$/i;
const HEADING = /^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$/;
const LIST = /^\s*(?:[-*+]|\d{1,9}[.)])\s+/;
const TABLE_SEP = /^[\s|:-]*-[\s|:-]*$/;
const CLOSERS = "\"'”’)\\]}»」』";
const SENTENCE = new RegExp(`[.!?][${CLOSERS}]*(?=\\s|$)|[。！？][${CLOSERS}]*`, "g");
const JOIN = "\n\n";
const encoder = new TextEncoder();

const utf8 = (s: string): number => encoder.encode(s).length;
export const countTokens = (s: string): number => { const n = utf8(s); return n === 0 ? 0 : Math.ceil(n / 3); };
const collapse = (s: string): string => s.replace(/\s+/g, " ").trim();

function linesPart(kind: "list" | "table", lines: string[]): Part {
  const text = lines.map(collapse).filter(Boolean).join("\n");
  let header = 0;
  if (kind === "table") {
    const rows = text.split("\n");
    header = rows.length >= 2 && TABLE_SEP.test(rows[1]) ? rows[0].length + 1 + rows[1].length : (rows[0]?.length ?? 0);
  }
  return { kind, text, header };
}

function lineKind(line: string): Kind {
  if (line.trim().startsWith("|")) return "table";
  if (LIST.test(line)) return "list";
  return "para";
}

function blocks(md: string): Part[] {
  const out: Part[] = [];
  let cur: string[] = [];
  let kind: Kind = "para";
  const close = () => {
    if (!cur.length) return;
    if (kind === "para") {
      const text = collapse(cur.join("\n"));
      if (text) out.push({ kind: "para", text, header: 0 });
    } else {
      const part = linesPart(kind as "list" | "table", cur);
      if (part.text) out.push(part);
    }
    cur = [];
  };
  for (const body of md.split(/\r\n|\r|\n/)) {
    if (!body.trim() || PAGE.test(body)) { close(); continue; }
    if (HEADING.test(body)) { close(); out.push({ kind: "heading", text: collapse(body), header: 0 }); continue; }
    const k = lineKind(body);
    if (cur.length && !(k === kind || (kind === "list" && k === "para"))) close();
    if (!cur.length) kind = k;
    cur.push(body);
  }
  close();
  return out;
}

/** UTF-8 byte counts of a text's prefixes, per UTF-16 index (a surrogate pair counts on its first half). */
function prefixBytes(text: string): number[] {
  const acc = [0];
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    const b = c < 0x80 ? 1 : c < 0x800 ? 2 : c >= 0xd800 && c <= 0xdbff ? 4 : c >= 0xdc00 && c <= 0xdfff ? 0 : 3;
    acc.push(acc[i] + b);
  }
  return acc;
}

function split(part: Part, prefix: number): [Part, Part | null] {
  const text = part.text;
  const acc = prefixBytes(text);
  const tokens = (c: number) => { const n = prefix + acc[c]; return n === 0 ? 0 : Math.ceil(n / 3); };
  const fits = (c: number) => tokens(c) <= MAX;
  const nearest = (cands: number[]): number | null => {
    let best: number | null = null;
    for (const c of cands) {
      if (!(c > 0 && c < text.length && fits(c))) continue;
      if (best === null || Math.abs(tokens(c) - TARGET) < Math.abs(tokens(best) - TARGET)
        || (Math.abs(tokens(c) - TARGET) === Math.abs(tokens(best) - TARGET) && c < best)) best = c;
    }
    return best;
  };
  if (part.kind === "table" && part.header && part.repeated) {   // a repeated header leads this part
    const rowEnd = text.indexOf("\n", part.header + 1);
    if (!fits(rowEnd < 0 ? text.length : rowEnd)) {   // it can't share a piece with a row: drop the repeat
      return split({ kind: "table", text: text.slice(part.repeated), header: 0 }, prefix);
    }
  }
  let cut: number | null = null;
  if (part.kind === "list" || part.kind === "table") {
    const lo = part.kind === "table" ? part.header : 0;
    const nl: number[] = [];
    for (let i = 0; i < text.length; i++) if (text[i] === "\n" && i > lo) nl.push(i);
    cut = nearest(nl);
  }
  if (cut === null) cut = nearest([...text.matchAll(SENTENCE)].map((m) => (m.index ?? 0) + m[0].length));
  if (cut === null) {
    for (let i = text.length - 1; i > 0; i--) if ((text[i] === " " || text[i] === "\n") && fits(i)) { cut = i; break; }
  }
  if (cut === null) {
    cut = 1;
    for (let c = text.length - 1; c >= 1; c--) {
      const low = text.charCodeAt(c);
      if (low >= 0xdc00 && low <= 0xdfff) continue;  // never between the halves of a pair
      if (fits(c)) { cut = c; break; }
    }
  }
  const head: Part = { kind: part.kind, text: text.slice(0, cut).trimEnd(), header: 0 };
  let a = cut;
  while (a < text.length && /\s/.test(text[a])) a++;
  if (a >= text.length) return [head, null];
  let rest: Part = { kind: part.kind, text: text.slice(a), header: 0 };
  if (part.kind === "table" && part.header && cut > part.header) {
    const hdr = text.slice(0, part.header);
    rest = { kind: "table", text: `${hdr}\n${rest.text}`, header: hdr.length, repeated: hdr.length + 1 };
  }
  return [head, rest];
}

interface Open { heads: Part[]; path: string | null; nearest: string | null; parts: Part[] }
const pieceText = (p: Open, extra?: Part): string => [...p.heads, ...p.parts, ...(extra ? [extra] : [])].map((x) => x.text).join(JOIN);
const prefixOf = (p: Open): number => (p.heads.length ? utf8(p.heads.map((h) => h.text).join(JOIN) + JOIN) : 0);

export function pack(markdown: string): Piece[] {
  let heads: [number, string][] = [];
  let pending: Part[] = [];
  const done: Open[] = [];
  let cur: Open | null = null;
  const close = () => { if (cur && cur.parts.length) done.push(cur); cur = null; };
  for (const b of blocks(markdown)) {
    if (b.kind === "heading") {
      close();
      const m = HEADING.exec(b.text)!;
      const level = m[1].length;
      heads = [...heads.filter(([l]) => l < level), [level, m[2].trim()]];
      pending.push(b);
      continue;
    }
    let rest: Part | null = b;
    while (rest) {
      if (!cur) {
        const path = heads.map(([, t]) => t).join(" › ") || null;
        cur = { heads: pending, path, nearest: heads.length ? heads[heads.length - 1][1] : null, parts: [] };
        pending = [];
      }
      if (countTokens(pieceText(cur, rest)) <= MAX) {
        cur.parts.push(rest);
        rest = null;
        if (countTokens(pieceText(cur)) >= TARGET) close();
      } else if (cur.parts.length) {
        close();
      } else {
        const [head, next] = split(rest, prefixOf(cur));
        cur.parts.push(head);
        rest = next;
        close();
      }
    }
  }
  close();
  return done.map((p, i) => ({ text: pieceText(p), locator: p.nearest ? `§ ${p.nearest}` : `¶ ${i + 1}`, heading: p.path }));
}
