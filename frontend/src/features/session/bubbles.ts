// Chat bubbles (docs/ai/03 C5; reply-display spec; ai-foundation design D21). Display only: a reply stays ONE message
// with one emotion, trace, energy charge, regenerate and copy. The model writes one short message per line; each
// line becomes a bubble (or, in watch, a script line under one name tape).
//
// Rules: split on line breaks; blank lines collapse; never split inside a fenced code block or between consecutive
// list lines (the chat prompt asks for plain text, so these are a safety net); at most MAX_BUBBLES, extra lines join
// the last one. Re-run on every streamed update, so a new bubble opens as soon as a line break arrives.

export const MAX_BUBBLES = 4;

const LIST_ITEM = /^\s*(?:[-*+•]|\d{1,3}[.)])\s+/;
const FENCE = /^\s*(```|~~~)/;

export function splitBubbles(text: string, max: number = MAX_BUBBLES): string[] {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const groups: string[][] = [];
  let fence: string[] | null = null;
  for (const line of lines) {
    if (fence) {
      fence.push(line);
      if (FENCE.test(line)) fence = null;
      continue;
    }
    if (FENCE.test(line)) {
      fence = [line];
      groups.push(fence);
      continue;
    }
    if (!line.trim()) continue; // blank lines collapse
    const prev = groups[groups.length - 1];
    const prevLast = prev?.[prev.length - 1];
    if (prev && prevLast !== undefined && LIST_ITEM.test(line) && LIST_ITEM.test(prevLast)) {
      prev.push(line); // consecutive list lines stay together
      continue;
    }
    groups.push([line]);
  }
  const bubbles = groups.map((g) => g.join("\n").trim()).filter((b) => b.length > 0);
  if (bubbles.length <= max) return bubbles;
  return [...bubbles.slice(0, max - 1), bubbles.slice(max - 1).join("\n")];
}
