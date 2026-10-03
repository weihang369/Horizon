// Builds the machine-readable contract (JSON Schema 2020-12) from the zod schemas in src/contract/schemas.ts.
// The backend (M1b+) validates every response and SSE event against it, so the output must be deterministic:
// recursive key sort, LF line endings, trailing newline, no timestamps.
import { z } from "zod";
import * as S from "../../src/contract/schemas";
import { SCHEMA_VERSION } from "../../src/contract/types";

export const CONTRACT_REV = "1.3";

/** Every exported `<Name>Schema` that is a zod type becomes `$defs/<Name>`. */
export function contractSchemas(): [name: string, schema: z.ZodType][] {
  return (Object.entries(S) as [string, unknown][])
    .filter((e): e is [string, z.ZodType] => e[0].endsWith("Schema") && e[1] instanceof z.ZodType)
    .map(([k, v]): [string, z.ZodType] => [k.slice(0, -"Schema".length), v])
    .sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0)); // code-unit order: locale-independent
}

function sortKeys(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(sortKeys);
  if (v && typeof v === "object") {
    return Object.fromEntries(Object.keys(v as object).sort().map((k) => [k, sortKeys((v as Record<string, unknown>)[k])]));
  }
  return v;
}

export function buildSchemaDocument(): Record<string, unknown> {
  const registry = z.registry<{ id: string }>();
  for (const [name, schema] of contractSchemas()) registry.add(schema, { id: name });
  const out = z.toJSONSchema(registry, {
    target: "draft-2020-12",
    io: "output",
    unrepresentable: "any",
    uri: (id) => `#/$defs/${id}`,
    override: (ctx) => {
      // Refinements are dropped by the converter; restore what the backend can still check.
      if (ctx.zodSchema === S.isoDate) ctx.jsonSchema.format = "date-time";
      if (ctx.zodSchema === S.assetUrl) ctx.jsonSchema.pattern = "^(/assets/|data:|placeholder:)";
    },
  });
  const defs: Record<string, unknown> = {};
  for (const [id, schema] of Object.entries(out.schemas)) {
    const { $schema: _drop, $id: _id, ...rest } = schema as Record<string, unknown>;
    defs[id] = rest;
  }
  return sortKeys({
    $schema: "https://json-schema.org/draft/2020-12/schema",
    $id: "https://github.com/horizon/contract/schema.json",
    title: "Horizon data contract",
    description: `Generated from frontend/src/contract/schemas.ts by \`npm run export-schema\`. Do not edit. Contract rev ${CONTRACT_REV}; fixtures carry schemaVersion ${SCHEMA_VERSION}.`,
    "x-contract-rev": CONTRACT_REV,
    "x-schema-version": SCHEMA_VERSION,
    $defs: defs,
  }) as Record<string, unknown>;
}

export function buildSchemaJson(): string {
  return `${JSON.stringify(buildSchemaDocument(), null, 2)}\n`;
}
