import react from "@vitejs/plugin-react";
import { createReadStream, existsSync, statSync } from "node:fs";
import { cp, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Plugin } from "vite";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";
import { resolveClient } from "./scripts/build/clientGuard.ts";

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

  // The local backend behind `/api` and `/assets/gen`: :8000 for `npm run dev`; the E2E HTTP project points it at its own
  // test backend (http-client-parity D8).
  const API_TARGET = process.env.HORIZON_API_TARGET || "http://127.0.0.1:8000";

  export default defineConfig(({ mode, command }) => {
    // Fails a dev server or build whose client choice is a typo, or that would ship the HttpClient where it must not (D14).
    resolveClient({ value: loadEnv(mode, here, "VITE_").VITE_HORIZON_CLIENT, mode, command, vercel: process.env.VERCEL === "1" });
    return {
    plugins: [react(), seedAssets()],
    resolve: {
      alias: {
        "@": path.resolve(here, "src"),
        "@seed": SEED_DIR,
      },
    },
    server: {
      fs: { allow: [here, SEED_DIR] },
      // `npm run dev` at the repo root (doc backend/01 §8): the API and generated assets come from the backend
      // (API_TARGET, :8000 by default). SSE passes through unbuffered (the backend sends no-cache +
      // X-Accel-Buffering: no). Seed placeholders under /assets/placeholder are still served by the seedAssets plugin.
      proxy: {
        "/api": { target: API_TARGET, changeOrigin: true },
        "/assets/gen": { target: API_TARGET, changeOrigin: true },
      },
    },
    build: {
      chunkSizeWarningLimit: 600,
    },
    test: {
      environment: "node",
      include: ["src/**/*.test.ts", "src/**/*.test.tsx", "scripts/**/*.test.ts"],
      // The HTTP contract run needs a backend: `npm run test:http` (vitest.http.config.ts) starts one.
      exclude: ["**/node_modules/**", "src/**/*.http.test.ts"],
    },
  };
});
