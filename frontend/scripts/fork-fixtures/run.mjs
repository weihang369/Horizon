// Entry point: loads the TypeScript fixture build through a short-lived Vite SSR loader (like scripts/seed-build).
//   node scripts/fork-fixtures/run.mjs build|check
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const here = path.dirname(fileURLToPath(import.meta.url));
const frontend = path.resolve(here, "../..");
const seedDir = path.resolve(frontend, "../seed");
const outDir = path.resolve(frontend, "../backend/tests/fixtures");
const mode = process.argv[2] === "check" ? "check" : "build";

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
  code = await mod.main(mode, seedDir, outDir);
} finally {
  await server.close();
}
process.exit(code);
