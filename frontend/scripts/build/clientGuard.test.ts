import { describe, expect, it } from "vitest";
import { resolveClient } from "./clientGuard";

const dev = { mode: "development", command: "serve" as const, vercel: false };
const build = { mode: "production", command: "build" as const, vercel: false };

describe("client guard (http-client-parity D14)", () => {
  it("unset, empty and mock mean the MockClient", () => {
    expect(resolveClient({ value: undefined, ...build })).toBe("mock");
    expect(resolveClient({ value: "", ...build })).toBe("mock");
    expect(resolveClient({ value: "mock", ...dev })).toBe("mock");
  });

  it("a misspelt value fails instead of silently meaning mock", () => {
    expect(() => resolveClient({ value: "HTTP", ...build })).toThrow(/VITE_HORIZON_CLIENT must be unset, "mock" or "http"/);
    expect(() => resolveClient({ value: "htp", ...dev })).toThrow(/VITE_HORIZON_CLIENT/);
  });

  it("the dev server may use http (npm run dev, --mode http)", () => {
    expect(resolveClient({ value: "http", ...dev, mode: "http" })).toBe("http");
    expect(resolveClient({ value: "http", ...dev })).toBe("http");
  });

  it("a build bundles the HttpClient only in --mode http (npm run demo)", () => {
    expect(resolveClient({ value: "http", ...build, mode: "http" })).toBe("http");
    expect(() => resolveClient({ value: "http", ...build })).toThrow(/needs `--mode http`/);
  });

  it("Vercel never gets the HttpClient, in any mode", () => {
    expect(() => resolveClient({ value: "http", ...build, mode: "http", vercel: true })).toThrow(/not allowed on Vercel/);
    expect(() => resolveClient({ value: "http", ...dev, vercel: true })).toThrow(/not allowed on Vercel/);
    expect(resolveClient({ value: undefined, ...build, vercel: true })).toBe("mock");
  });
});
