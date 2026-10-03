// export-schema: writes backend/horizon/contract/schema.json, or (check) fails when the committed file is stale.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { buildSchemaJson, contractSchemas } from "./schema";

export async function main(mode: "write" | "check", outFile: string): Promise<number> {
  const json = buildSchemaJson();
  const rel = path.relative(process.cwd(), outFile);
  if (mode === "check") {
    let current = "";
    try {
      current = readFileSync(outFile, "utf8");
    } catch {
      // missing file = stale
    }
    if (current !== json) {
      console.error(`[export-schema:check] ${rel} is out of date. Run: npm run export-schema`);
      return 1;
    }
    console.log(`[export-schema:check] OK: ${rel} matches (${contractSchemas().length} definitions).`);
    return 0;
  }
  mkdirSync(path.dirname(outFile), { recursive: true });
  writeFileSync(outFile, json, { encoding: "utf8" });
  console.log(`[export-schema] ${contractSchemas().length} definitions → ${rel}`);
  return 0;
}
