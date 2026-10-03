// Tiny, safe Markdown → React renderer for chat messages (CHAT-02 AC4). Owner: C.
// Bold, italics, inline code, fenced code, links (http/https/mailto only), bullet and numbered lists, quotes.
// Raw HTML is never interpreted: everything is emitted as React text nodes (escaped by React).
// Rendered only on turn.end (R12); streaming text stays plain.
// D-59: `[n]` markers with a matching citation become `cite` nodes (never inside code); others stay literal text.
import type { ReactNode } from "react";

export type MdBlock =
  | { type: "p"; text: string }
  | { type: "ul" | "ol"; items: string[]; start?: number }
  | { type: "code"; text: string; lang?: string }
  | { type: "quote"; text: string }
  | { type: "h"; text: string };

export type MdInline =
  | { type: "text"; text: string }
  | { type: "code"; text: string }
  | { type: "strong"; children: MdInline[] }
  | { type: "em"; children: MdInline[] }
  | { type: "link"; href: string; children: MdInline[] }
  | { type: "cite"; n: number };

/** Renders a citation marker (D-59). */
export type CiteRenderer = (n: number, key: string) => ReactNode;
export interface MdOptions { cites?: ReadonlySet<number>; renderCite?: CiteRenderer }

const UL = /^\s{0,3}[-*+]\s+(.*)$/;
const OL = /^\s{0,3}(\d{1,3})[.)]\s+(.*)$/;
const FENCE = /^\s{0,3}```\s*([\w-]*)\s*$/;
const QUOTE = /^\s{0,3}>\s?(.*)$/;
const HEAD = /^\s{0,3}#{1,6}\s+(.*)$/;

/** Split source text into blocks. */
export function parseBlocks(src: string): MdBlock[] {
  const lines = src.replace(/\r\n?/g, "\n").split("\n");
  const out: MdBlock[] = [];
  let para: string[] = [];
  const flush = () => {
    if (para.length) out.push({ type: "p", text: para.join("\n") });
    para = [];
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const fence = FENCE.exec(line);
    if (fence) {
      flush();
      const body: string[] = [];
      i++;
      while (i < lines.length && !FENCE.test(lines[i])) body.push(lines[i++]);
      out.push({ type: "code", text: body.join("\n"), ...(fence[1] ? { lang: fence[1] } : {}) });
      continue;
    }
    if (!line.trim()) {
      flush();
      continue;
    }
    const ul = UL.exec(line);
    const ol = OL.exec(line);
    if (ul || ol) {
      flush();
      const kind = ul ? "ul" : "ol";
      const items: string[] = [];
      const start = ol ? Number(ol[1]) : undefined;
      while (i < lines.length) {
        const m = kind === "ul" ? UL.exec(lines[i]) : OL.exec(lines[i]);
        if (m) items.push(kind === "ul" ? m[1] : m[2]);
        else if (lines[i].trim() && /^\s{2,}/.test(lines[i]) && items.length) items[items.length - 1] += ` ${lines[i].trim()}`;
        else break;
        i++;
      }
      i--;
      out.push(kind === "ol" && start !== undefined && start !== 1 ? { type: "ol", items, start } : { type: kind, items });
      continue;
    }
    const q = QUOTE.exec(line);
    if (q) {
      flush();
      const body = [q[1]];
      while (i + 1 < lines.length && QUOTE.test(lines[i + 1])) body.push(QUOTE.exec(lines[++i])![1]);
      out.push({ type: "quote", text: body.join("\n") });
      continue;
    }
    const h = HEAD.exec(line);
    if (h) {
      flush();
      out.push({ type: "h", text: h[1] });
      continue;
    }
    para.push(line);
  }
  flush();
  return out;
}

const SAFE_HREF = /^(https?:\/\/|mailto:)/i;

const CITE = /^\[(\d{1,2})\]/;

/** Parse inline spans. Unclosed markers stay literal. `cites`: marker numbers that have a citation. */
export function parseInline(src: string, cites?: ReadonlySet<number>): MdInline[] {
  const out: MdInline[] = [];
  let buf = "";
  const pushText = () => {
    if (buf) out.push({ type: "text", text: buf });
    buf = "";
  };
  let i = 0;
  while (i < src.length) {
    const ch = src[i];
    if (ch === "\\" && i + 1 < src.length && /[\\`*_[\]()#>-]/.test(src[i + 1])) {
      buf += src[i + 1];
      i += 2;
      continue;
    }
    if (ch === "`") {
      const end = src.indexOf("`", i + 1);
      if (end > i + 1) {
        pushText();
        out.push({ type: "code", text: src.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    }
    if (ch === "[" && cites?.size) {
      const cm = CITE.exec(src.slice(i, i + 5));
      if (cm && cites.has(Number(cm[1])) && src[i + cm[0].length] !== "(") {
        pushText();
        out.push({ type: "cite", n: Number(cm[1]) });
        i += cm[0].length;
        continue;
      }
    }
    if (ch === "[") {
      const close = src.indexOf("]", i + 1);
      if (close > i && src[close + 1] === "(") {
        const end = src.indexOf(")", close + 2);
        const href = end > close ? src.slice(close + 2, end).trim() : "";
        if (end > close && SAFE_HREF.test(href)) {
          pushText();
          out.push({ type: "link", href, children: parseInline(src.slice(i + 1, close), cites) });
          i = end + 1;
          continue;
        }
      }
    }
    if ((ch === "*" || ch === "_") && src[i + 1] === ch) {
      const marker = ch + ch;
      const end = src.indexOf(marker, i + 2);
      if (end > i + 2) {
        pushText();
        out.push({ type: "strong", children: parseInline(src.slice(i + 2, end), cites) });
        i = end + 2;
        continue;
      }
    }
    if (ch === "*" || ch === "_") {
      const prev = src[i - 1];
      const next = src[i + 1];
      // `_` inside words (snake_case) is literal; `*` needs a non-space right after it.
      const opens = next !== undefined && next !== " " && next !== ch && !(ch === "_" && prev && /\w/.test(prev));
      if (opens) {
        let end = -1;
        for (let j = i + 1; j < src.length; j++) {
          if (src[j] === ch && src[j - 1] !== " " && src[j + 1] !== ch && !(ch === "_" && src[j + 1] && /\w/.test(src[j + 1]))) {
            end = j;
            break;
          }
        }
        if (end > i + 1) {
          pushText();
          out.push({ type: "em", children: parseInline(src.slice(i + 1, end), cites) });
          i = end + 1;
          continue;
        }
      }
    }
    buf += ch;
    i++;
  }
  pushText();
  return out;
}

function renderInline(nodes: MdInline[], key = "i", cite?: CiteRenderer): ReactNode[] {
  return nodes.map((n, idx) => {
    const k = `${key}.${idx}`;
    switch (n.type) {
      case "text": return withBreaks(n.text, k);
      case "code": return <code key={k}>{n.text}</code>;
      case "strong": return <strong key={k}>{renderInline(n.children, k, cite)}</strong>;
      case "em": return <em key={k}>{renderInline(n.children, k, cite)}</em>;
      case "link": return <a key={k} href={n.href} target="_blank" rel="noreferrer noopener">{renderInline(n.children, k, cite)}</a>;
      case "cite": return cite ? cite(n.n, k) : `[${n.n}]`;
    }
    return null;
  });
}

function withBreaks(text: string, key: string): ReactNode {
  if (!text.includes("\n")) return text;
  const parts = text.split("\n");
  return parts.flatMap((p, i) => (i ? [<br key={`${key}b${i}`} />, p] : [p]));
}

/** Render Markdown source as React nodes (no raw HTML, ever). */
export function renderMarkdown(src: string, opts: MdOptions = {}): ReactNode {
  const cites = opts.renderCite ? opts.cites : undefined;
  const inl = (text: string, k: string) => renderInline(parseInline(text, cites), k, opts.renderCite);
  return parseBlocks(src).map((b, i) => {
    const k = `b${i}`;
    switch (b.type) {
      case "p": return <p key={k}>{inl(b.text, k)}</p>;
      case "h": return <p key={k}><strong>{inl(b.text, k)}</strong></p>;
      case "quote": return <blockquote key={k}>{inl(b.text, k)}</blockquote>;
      case "code": return <pre key={k}><code>{b.text}</code></pre>;
      case "ul": return <ul key={k}>{b.items.map((it, j) => <li key={j}>{inl(it, `${k}.${j}`)}</li>)}</ul>;
      case "ol": return <ol key={k} start={b.start}>{b.items.map((it, j) => <li key={j}>{inl(it, `${k}.${j}`)}</li>)}</ol>;
    }
    return null;
  });
}

/** Strip Markdown markers for plain displays (backlog search, cut-ins, copy). */
export function plainText(src: string): string {
  const flat = (n: MdInline[]): string => n.map((x) => (x.type === "text" || x.type === "code" ? x.text : x.type === "cite" ? `[${x.n}]` : flat(x.children))).join("");
  return parseBlocks(src)
    .map((b) => {
      if (b.type === "code") return b.text;
      if ("items" in b) return b.items.map((it) => `• ${flat(parseInline(it))}`).join("\n");
      return flat(parseInline(b.text));
    })
    .join("\n");
}

/** Split plain text into text runs and cited marker numbers (Backlog, streaming). `cites` undefined = every marker. */
export function splitMarkers(text: string, cites?: ReadonlySet<number>): (string | number)[] {
  const out: (string | number)[] = [];
  let at = 0;
  for (const m of text.matchAll(/\[(\d{1,2})\](?!\()/g)) {
    const n = Number(m[1]);
    if (cites && !cites.has(n)) continue;
    if (m.index > at) out.push(text.slice(at, m.index));
    out.push(n);
    at = m.index + m[0].length;
  }
  if (at < text.length) out.push(text.slice(at));
  return out;
}
