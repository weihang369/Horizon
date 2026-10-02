import react from "@vitejs/plugin-react";
import { createReadStream, existsSync, statSync } from "node:fs";
import { cp, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

const here = path.dirname(fileURLToPath(import.meta.url));
const SEED_DIR = path.resolve(here, "../seed");
const SEED_ASSETS = path.join(SEED_DIR, "assets");

const MIME: Record<string, string> = {
  ".svg": "image/svg+xml",
  ".webp": "image/webp",
  ".avif": "image/avif",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".json": "application/json",
  ".opus": "audio/ogg",
  ".ogg": "audio/ogg",
  ".mp3": "audio/mpeg",
  ".aac": "audio/aac",
  ".m4a": "audio/mp4",
};

/**
 * Serves repo-root `seed/assets` at `/assets` (doc 05 §1: relative asset URLs, identical for mock and backend).
 * In builds the folder is copied into `dist/assets/` (next to Vite's hashed bundles; names never collide).
 */
function seedAssets(): Plugin {
  let outDir = "dist";
  return {
    name: "horizon-seed-assets",
    configResolved(cfg) {
      outDir = path.resolve(cfg.root, cfg.build.outDir);
    },
    configureServer(server) {
      server.middlewares.use("/assets", (req, res, next) => {
        const url = decodeURIComponent((req.url ?? "/").split("?")[0]);
        const file = path.join(SEED_ASSETS, url);
        if (!file.startsWith(SEED_ASSETS) || !existsSync(file) || !statSync(file).isFile()) return next();
        res.setHeader("Content-Type", MIME[path.extname(file).toLowerCase()] ?? "application/octet-stream");
        res.setHeader("Cache-Control", "no-cache");
        createReadStream(file).pipe(res);
      });
    },
    async closeBundle() {
      if (!existsSync(SEED_ASSETS)) return;
      const dest = path.join(outDir, "assets");
      await mkdir(dest, { recursive: true });
      await cp(SEED_ASSETS, dest, { recursive: true });
    },
  };
}

export default defineConfig({
  plugins: [react(), seedAssets()],
  resolve: {
    alias: {
      "@": path.resolve(here, "src"),
      "@seed": SEED_DIR,
    },
  },
  server: {
    fs: { allow: [here, SEED_DIR] },
  },
  build: {
    chunkSizeWarningLimit: 600,
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "scripts/**/*.test.ts"],
  },
});
