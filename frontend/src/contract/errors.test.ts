// HorizonError (contract rev 1.3): the new codes and the optional `details` survive serialisation.
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { DEFAULT_RETRYABLE, ERROR_COPY, HorizonError, toHorizonError } from "./errors";
import { HorizonErrorShapeSchema } from "./schemas";

describe("HorizonError", () => {
  it("round-trips details through toJSON", () => {
    const e = new HorizonError("conflict", "Another session is live.", { details: { activeSessionId: "ses_abc" } });
    const json = JSON.parse(JSON.stringify(e.toJSON()));
    expect(json).toEqual({ code: "conflict", message: "Another session is live.", retryable: false, details: { activeSessionId: "ses_abc" } });
    expect(HorizonErrorShapeSchema.safeParse(json).success).toBe(true);
  });

  it("rev 1.3 codes are not retryable and have copy", () => {
    for (const code of ["not_found", "validation", "conflict"] as const) {
      expect(DEFAULT_RETRYABLE[code]).toBe(false);
      expect(ERROR_COPY[code].length).toBeGreaterThan(0);
      expect(new HorizonError(code).retryable).toBe(false);
    }
  });

  it("keeps details when normalising an existing HorizonError", () => {
    const e = new HorizonError("validation", "Too many sources.", { details: { limit: 20 } });
    expect(toHorizonError(e).details).toEqual({ limit: 20 });
  });

  it("default retryable flags match the shared table the backend also checks (backend/tests/fixtures/errors)", () => {
    const file = path.resolve(__dirname, "../../../backend/tests/fixtures/errors/codes.json");
    const { codes } = JSON.parse(readFileSync(file, "utf8")) as { codes: Record<string, { retryable: boolean }> };
    expect(Object.fromEntries(Object.entries(codes).map(([k, v]) => [k, v.retryable]))).toEqual(DEFAULT_RETRYABLE);
  });
});
