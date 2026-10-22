// U-59 (the user's choice): a Knowledge row shows the part of its passage that matched, not the passage's first lines
// (Hana's cited ¶ 2 began "p. 6. Fishing-day rice balls…" while the line it was cited for is its last). Owner: AI.

const STOP = new Set([
  "about", "after", "again", "also", "and", "because", "been", "before", "being", "could", "does", "doing", "from", "have",
  "having", "into", "just", "more", "most", "much", "only", "other", "over", "should", "some", "such", "than", "that", "their",
  "them", "then", "there", "these", "they", "this", "those", "very", "were", "what", "when", "where", "which", "while", "with",
  "would", "your", "you're", "it's",
]);

/** The words a sentence can match on: lower case, 4+ letters, no stop words. */
export function words(text: string): Set<string> {
  return new Set((text.toLowerCase().match(/[\p{L}\p{N}][\p{L}\p{N}'-]*/gu) ?? []).filter((w) => w.length >= 4 && !STOP.has(w)));
}

/** The passage split into sentences, each with its start offset. A line break always ends one; a full stop only after
 * a word of 3+ letters (or a closing quote), so "p. 12." or "Dr." stays inside its sentence. */
function sentences(text: string): { start: number; text: string }[] {
  const starts = [0];
  const re = /(?:\p{L}{3,}|["')\]])[.!?]+["')\]]*[ \t]+|\n+/gu;
  for (let m = re.exec(text); m; m = re.exec(text)) starts.push(m.index + m[0].length);
  return starts
    .map((start, i) => ({ start, text: text.slice(start, starts[i + 1] ?? text.length) }))
    .filter((x) => x.text.trim());
}

/** The reply's sentence that carries marker `[n]` (where a cited passage was used), or "" when there is none. */
export function citingSentence(reply: string, n: number): string {
  const at = reply.indexOf(`[${n}]`);
  if (at < 0) return "";
  const start = Math.max(reply.lastIndexOf(". ", at), reply.lastIndexOf("\n", at)) + 1;
  return reply.slice(start, at);
}

/** The passage from its best-matching sentence on, "…" first when that isn't the start. `probe`: what it was found or
 * cited for. No overlap at all: the passage as it is. */
export function focusSnippet(text: string, probe: string): string {
  const want = words(probe);
  if (!want.size) return text;
  let best = { score: 0, start: 0 };
  for (const s of sentences(text)) {
    let score = 0;
    for (const w of words(s.text)) if (want.has(w)) score++;
    if (score > best.score) best = { score, start: s.start };
  }
  if (best.score === 0 || best.start === 0) return text;
  return `…${text.slice(best.start).trimStart()}`;
}
