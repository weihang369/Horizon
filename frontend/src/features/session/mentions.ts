// @mentions (O11, UXA §2.3): pure text helpers + a tiny bus shared by the Composer (owns focus and keys)
// and the MentionPicker popover (renders the rows). Mentions are atomic `@Name` tokens in the draft.
import { createStore } from "zustand/vanilla";

export interface MentionCandidate { id: string; name: string }

/** The `@query` being typed at the caret, if any. */
export function mentionQueryAt(text: string, caret: number): { start: number; query: string } | null {
  const before = text.slice(0, caret);
  const m = /(^|\s)@([\p{L}\p{N}_-]{0,24})$/u.exec(before);
  if (!m) return null;
  return { start: caret - m[2].length - 1, query: m[2] };
}

export function filterCandidates(all: MentionCandidate[], query: string): MentionCandidate[] {
  const q = query.toLowerCase();
  return all.filter((c) => c.name.toLowerCase().startsWith(q) || (q.length > 1 && c.name.toLowerCase().includes(q))).slice(0, 5);
}

/** Replace the `@query` at `start` with `@Name ` and return the new text + caret. */
export function insertMention(text: string, start: number, caret: number, name: string): { text: string; caret: number } {
  const token = `@${name} `;
  const next = text.slice(0, start) + token + text.slice(caret).replace(/^ /, "");
  return { text: next, caret: start + token.length };
}

export interface MentionSpan { start: number; end: number; id: string }

/** Every `@Name` token for a known candidate (case-sensitive name, word boundary after). */
export function mentionSpans(text: string, all: MentionCandidate[]): MentionSpan[] {
  if (!all.length || !text.includes("@")) return [];
  const out: MentionSpan[] = [];
  const names = [...all].sort((a, b) => b.name.length - a.name.length);
  for (let i = 0; i < text.length; i++) {
    if (text[i] !== "@" || (i > 0 && !/\s/.test(text[i - 1]))) continue;
    for (const c of names) {
      const end = i + 1 + c.name.length;
      if (text.slice(i + 1, end) === c.name && (end === text.length || !/[\p{L}\p{N}_]/u.test(text[end]))) {
        out.push({ start: i, end, id: c.id });
        i = end - 1;
        break;
      }
    }
  }
  return out;
}

export const mentionIds = (text: string, all: MentionCandidate[]): string[] => [...new Set(mentionSpans(text, all).map((s) => s.id))];

/** Backspace right after a mention removes the whole chip. Returns null when not applicable. */
export function backspaceMention(text: string, caret: number, all: MentionCandidate[]): { text: string; caret: number } | null {
  const span = mentionSpans(text, all).find((s) => s.end === caret || (s.end + 1 === caret && text[s.end] === " "));
  if (!span) return null;
  const cut = text[span.end] === " " && span.end + 1 === caret ? span.end + 1 : span.end;
  return { text: text.slice(0, span.start) + text.slice(cut), caret: span.start };
}

// ── Bus (composer ⇄ picker) ─────────────────────────────────────────────────
export interface MentionBus { items: MentionCandidate[]; active: number }
export const mentionBus = createStore<MentionBus>(() => ({ items: [], active: 0 }));
export function moveMention(delta: number): void {
  mentionBus.setState((s) => ({ active: s.items.length ? (s.active + delta + s.items.length) % s.items.length : 0 }));
}
