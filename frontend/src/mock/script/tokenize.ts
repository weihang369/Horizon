// Splits text into ~4-character "tokens" (leading whitespace attached), then groups them into deltas.

export function tokenize(text: string, charsPerToken = 4): string[] {
  const out: string[] = [];
  const re = /(\s*)(\S+)/g;
  let m: RegExpExecArray | null;
  let consumed = 0;
  while ((m = re.exec(text))) {
    const [, ws, word] = m;
    let first = true;
    for (let i = 0; i < word.length; i += charsPerToken) {
      out.push((first ? ws : "") + word.slice(i, i + charsPerToken));
      first = false;
    }
    consumed = re.lastIndex;
  }
  if (consumed < text.length) {
    const tail = text.slice(consumed);
    if (out.length) out[out.length - 1] += tail;
    else out.push(tail);
  }
  return out;
}

export function chunkTokens(tokens: string[], perChunk: number): string[] {
  const out: string[] = [];
  for (let i = 0; i < tokens.length; i += perChunk) out.push(tokens.slice(i, i + perChunk).join(""));
  return out;
}
