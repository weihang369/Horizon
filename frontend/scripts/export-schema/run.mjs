// Entry point: loads the TypeScript exporter through a short-lived Vite SSR loader (same pattern as seed-build).
//   node scripts/export-schema/run.mjs [--check]
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const here = path.dirname(fileURLToPath(import.meta.url));
const frontend = path.resolve(here, "../..");
const outFile = path.resolve(frontend, "../backend/horizon/contract/schema.json");
const mode = process.argv.includes("--check") ? "check" : "write";

const server = await createServer({
  root: frontend,
  configFile: false,
  logLevel: "error",
  appType: "custom",
  server: { middlewareMode: true, hmr: false, ws: false },
  optimizeDeps: { noDiscovery: true, include: [] },
});
let code = 1;
try {
  const mod = await server.ssrLoadModule(path.join(here, "build.ts"));
  code = await mod.main(mode, outFile);
} finally {
  await server.close();
}
process.exit(code);
