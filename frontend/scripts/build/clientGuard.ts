// Which HorizonClient a Vite run bundles, and the rules that keep the HttpClient out of builds that must not have it
// (http-client spec "Client selection", http-client-parity D14). Called from vite.config.ts for every dev server,
// build and vitest run. Owner: SWE.
// - The value must be unset, "mock" or "http": a typo like "HTTP" fails instead of silently meaning mock.
// - "http" in a build needs `--mode http` (only `npm run demo` does that), so a stray env var can't flip a deploy.
// - A Vercel build (VERCEL=1) never bundles the HttpClient: production there is the MockClient (D-73).

export type ClientKind = "mock" | "http";

export interface ClientGuardInput {
  /** VITE_HORIZON_CLIENT as Vite resolved it (mode .env files + the environment). */
  value: string | undefined;
  /** Vite's mode ("development", "production", "http", "test", …). */
  mode: string;
  command: "serve" | "build";
  /** True when the VERCEL environment variable is "1". */
  vercel: boolean;
}

export function resolveClient({ value, mode, command, vercel }: ClientGuardInput): ClientKind {
  const v = value ?? "";
  if (v !== "" && v !== "mock" && v !== "http") {
    throw new Error(`VITE_HORIZON_CLIENT must be unset, "mock" or "http" (got ${JSON.stringify(v)}).`);
  }
  if (v !== "http") return "mock";
  if (vercel) {
    throw new Error("VITE_HORIZON_CLIENT=http is not allowed on Vercel: the deployed app is the MockClient (D-73).");
  }
  if (command === "build" && mode !== "http") {
    throw new Error(
      `VITE_HORIZON_CLIENT=http in a build needs \`--mode http\` (npm run demo); this build's mode is "${mode}". ` +
        "Unset the variable to build the MockClient.",
    );
  }
  return "http";
}
