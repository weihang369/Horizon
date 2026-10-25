import { describe, expect, it } from "vitest";
import { spendRows } from "./spend";

describe("spendRows", () => {
  it("sorts, drops zeros and caps", () => {
    expect(spendRows({ a: 0.01, b: 0, c: 0.05, d: 0.02 }, 2)).toEqual([{ id: "c", usd: 0.05 }, { id: "d", usd: 0.02 }]);
  });
});
