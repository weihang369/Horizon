// The backend's `count_tokens` (domain/pricing.py; docs/ai/04 P4, P10): ceil(UTF-8 bytes / 3), 0 for empty text.
// No tokenizer: it over-counts English and is close for CJK, the safe direction for a budget. The persona preview
// cuts with exactly this count, so it must stay byte-for-byte the backend's. Owner: AI.
const encoder = new TextEncoder();
export const BYTES_PER_TOKEN = 3;

export function utf8Bytes(text: string): number {
  return encoder.encode(text).length;
}

export function countTokens(text: string): number {
  const n = utf8Bytes(text);
  return n === 0 ? 0 : Math.ceil(n / BYTES_PER_TOKEN);
}
