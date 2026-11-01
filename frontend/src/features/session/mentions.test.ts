import { describe, expect, it } from "vitest";
import { backspaceMention, filterCandidates, insertMention, mentionIds, mentionNames, mentionQueryAt, mentionSpans } from "./mentions";

const cast = [{ id: "h", name: "Hana" }, { id: "t", name: "Takeshi" }, { id: "r", name: "Rin" }];

describe("mentions (O11)", () => {
  it("finds the @query at the caret only at a word start", () => {
    expect(mentionQueryAt("hi @Ha", 6)).toEqual({ start: 3, query: "Ha" });
    expect(mentionQueryAt("@", 1)).toEqual({ start: 0, query: "" });
    expect(mentionQueryAt("mail@x", 6)).toBeNull();
  });

  it("filters to ≤ 5 rows by prefix", () => {
    expect(filterCandidates(cast, "r").map((c) => c.id)).toEqual(["r"]);
    expect(filterCandidates(cast, "").length).toBe(3);
  });

  it("inserts an atomic token and extracts mention ids", () => {
    const r = insertMention("ask @Ta", 4, 7, "Takeshi");
    expect(r).toEqual({ text: "ask @Takeshi ", caret: 13 });
    expect(mentionIds(`${r.text}and @Rin!`, cast)).toEqual(["t", "r"]);
    expect(mentionSpans("@Rinny", cast)).toEqual([]);
  });

  it("backspace removes a whole chip", () => {
    expect(backspaceMention("hey @Hana ", 10, cast)).toEqual({ text: "hey ", caret: 4 });
    expect(backspaceMention("hey @Hana", 9, cast)).toEqual({ text: "hey ", caret: 4 });
    expect(backspaceMention("hey Hana", 8, cast)).toBeNull();
  });

  it("names a colliding first name in full, so each one can be mentioned (pass 2 J3-10)", () => {
    const people = [
      { id: "a", full: "Mei Lin", first: "Mei" }, { id: "b", full: "Mei Tanaka", first: "Mei" }, { id: "c", full: "Rin Sato", first: "Rin" },
    ];
    const names = mentionNames(people);
    expect(names.map((n) => n.name)).toEqual(["Mei Lin", "Mei Tanaka", "Rin"]);
    expect(mentionIds("@Mei Tanaka what now? @Rin", names)).toEqual(["b", "c"]);
    const twins = mentionNames([{ id: "x", full: "Ana Cruz", first: "Ana" }, { id: "y", full: "Ana Cruz", first: "Ana" }]);
    expect(twins.map((n) => n.name)).toEqual(["Ana Cruz", "Ana Cruz 2"]);
    expect(mentionIds("@Ana Cruz 2 hi", twins)).toEqual(["y"]);
  });
});
