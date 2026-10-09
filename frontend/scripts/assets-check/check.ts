// ASSETS.md check (asset-credits spec, http-client-parity D16): every shipped asset has a row, every row matches a
// shipped asset, and every row carries the provenance or credit its source needs. Pure functions over an inventory and
// the ASSETS.md text, so the rules are unit-tested without touching the repo. Offline: no network, no dependencies.
// Owner: SWE.

export type Source = "procedural" | "ai" | "library" | "font";
export const SOURCES: readonly Source[] = ["procedural", "ai", "library", "font"];

/** SPDX identifiers this project can use. Extend it when a new licence is genuinely needed (https://spdx.org/licenses/). */
export const SPDX = new Set([
  "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Unlicense", "0BSD",
  "CC0-1.0", "CC-BY-3.0", "CC-BY-4.0", "CC-BY-SA-3.0", "CC-BY-SA-4.0", "OFL-1.1",
]);

/** Fields an `ai` row's provenance cell must name (docs/requirements/06 §6: model, date, prompt, technique). */
export const AI_FIELDS = ["model", "date", "prompt", "technique"] as const;

export interface Inventory {
  /** Repo-relative POSIX paths of shipped files. */
  files: string[];
  /** Bundled font packages, e.g. "@fontsource/anton". */
  fonts: string[];
  /** System track id → its licence in seed/system-tracks.json. */
  tracks: Record<string, string>;
}

export interface Row {
  line: number;
  pattern: string;
  kind: string;
  source: string;
  credit: string;
  licence: string;
}

export const BEGIN = "<!-- assets:begin -->";
export const END = "<!-- assets:end -->";

/** The table rows between the markers (header and separator skipped). */
export function parseRows(md: string): Row[] {
  const lines = md.split(/\r?\n/);
  const b = lines.findIndex((l) => l.trim() === BEGIN);
  const e = lines.findIndex((l) => l.trim() === END);
  if (b < 0 || e < 0 || e < b) throw new Error(`ASSETS.md needs one table between ${BEGIN} and ${END}`);
  const rows: Row[] = [];
  for (let i = b + 1; i < e; i++) {
    const raw = lines[i].trim();
    if (!raw.startsWith("|")) continue;
    const cells = raw.replace(/^\||\|$/g, "").split("|").map((c) => c.trim().replace(/^`|`$/g, ""));
    if (cells[0] === "Pattern" || /^:?-+:?$/.test(cells[0])) continue;
    const [pattern = "", kind = "", source = "", credit = "", licence = ""] = cells;
    rows.push({ line: i + 1, pattern, kind, source, credit, licence });
  }
  return rows;
}

/** A path glob: `**` spans directories, `*` stays within one segment. */
export function globToRegExp(glob: string): RegExp {
  let re = "";
  for (let i = 0; i < glob.length; i++) {
    const ch = glob[i];
    if (ch === "*" && glob[i + 1] === "*") {
      re += ".*";
      i += 1;
      if (glob[i + 1] === "/") i += 1;
    } else if (ch === "*") re += "[^/]*";
    else re += ch.replace(/[.+?^${}()|[\]\\]/g, "\\$&");
  }
  return new RegExp(`^${re}$`);
}

type Item = { id: string; kind: "file" | "font" | "track" };

function items(inv: Inventory): Item[] {
  return [
    ...inv.files.map((f) => ({ id: f, kind: "file" as const })),
    ...inv.fonts.map((f) => ({ id: `npm:${f}`, kind: "font" as const })),
    ...Object.keys(inv.tracks).map((t) => ({ id: `track:${t}`, kind: "track" as const })),
  ];
}

function matches(row: Row, item: Item): boolean {
  if (row.pattern.startsWith("npm:") || row.pattern.startsWith("track:")) return row.pattern === item.id;
  return item.kind === "file" && globToRegExp(row.pattern).test(item.id);
}

/** `key=value; key=value` pairs in a provenance cell. */
export function fields(cell: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const part of cell.split(";")) {
    const m = /^\s*([a-z]+)\s*=\s*(.+?)\s*$/.exec(part);
    if (m) out[m[1]] = m[2];
  }
  return out;
}

export interface Result {
  problems: string[];
  assets: number;
  rows: number;
}

export function checkAssets(inv: Inventory, md: string): Result {
  const rows = parseRows(md);
  const all = items(inv);
  const problems: string[] = [];
  for (const it of all) {
    if (!rows.some((r) => matches(r, it))) problems.push(`no ASSETS.md row covers ${it.id}`);
  }
  for (const r of rows) {
    const where = `ASSETS.md line ${r.line} (${r.pattern || "empty pattern"})`;
    if (!r.pattern) problems.push(`${where}: missing pattern`);
    else if (!all.some((it) => matches(r, it))) problems.push(`${where}: matches no shipped asset`);
    if (!r.kind) problems.push(`${where}: missing kind`);
    if (!SOURCES.includes(r.source as Source)) problems.push(`${where}: source must be one of ${SOURCES.join(", ")} (got "${r.source}")`);
    if (!r.credit) problems.push(`${where}: missing credit / provenance`);
    if (!SPDX.has(r.licence)) problems.push(`${where}: "${r.licence}" is not a known SPDX licence identifier`);
    if (r.source === "ai") {
      const f = fields(r.credit);
      for (const k of AI_FIELDS) if (!f[k]) problems.push(`${where}: an ai row needs ${k}= in its provenance`);
    }
    if (r.pattern.startsWith("track:")) {
      const shipped = inv.tracks[r.pattern.slice("track:".length)];
      if (shipped !== undefined && shipped !== r.licence) {
        problems.push(`${where}: licence ${r.licence} disagrees with seed/system-tracks.json (${shipped})`);
      }
    }
  }
  return { problems, assets: all.length, rows: rows.length };
}
