// The Memory tab's paging (PRF-07; M13 memory design D37): the newest 50, then "Show more (n)" 50 at a time.
import { describe, expect, it } from "vitest";
import { MEMORY_PAGE, memoryPage } from "./tabs";

describe("Memory tab paging", () => {
  it("shows 50, then 50 more, with the count left", () => {
    const items = Array.from({ length: 120 }, (_, i) => i);
    expect(MEMORY_PAGE).toBe(50);
    const first = memoryPage(items, MEMORY_PAGE);
    expect(first.visible).toHaveLength(50);
    expect(first.more).toBe(70);
    const second = memoryPage(items, MEMORY_PAGE * 2);
    expect(second.visible[99]).toBe(99);
    expect(second.more).toBe(20);
    expect(memoryPage(items, MEMORY_PAGE * 3)).toEqual({ visible: items, more: 0 });
  });

  it("has no Show more under a page", () => {
    expect(memoryPage([1, 2, 3], MEMORY_PAGE)).toEqual({ visible: [1, 2, 3], more: 0 });
  });
});
