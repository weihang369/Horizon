// Demo parity for bubbles (D-46; ai-foundation design D22; task 4.3): chat-mode character lines in the recorded
// sessions and the mock banks may hold line breaks (shown as up to 4 bubbles); debate lines never do.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import type { Message, Session } from "../contract/types";
import { debateLine } from "./banks/generic";
import { SEED_BANKS } from "./banks/seedBanks";

const SEED = path.resolve(__dirname, "../../../seed");
const dirs = ["sessions", "_mock/sessions"].flatMap((d) => (existsSync(path.join(SEED, d)) ? readdirSync(path.join(SEED, d)).map((s) => `${d}/${s}`) : []));
const read = <T,>(rel: string) => (JSON.parse(readFileSync(path.join(SEED, rel), "utf8")) as { data: T }).data;
const lines = (dir: string) => read<Message[]>(`${dir}/messages.json`).filter((m) => m.author.type === "character");

describe("demo line breaks", () => {
  it("no debate message contains a line break", () => {
    const debates = dirs.filter((d) => read<Session>(`${d}/session.json`).mode === "debate");
    expect(debates.length).toBeGreaterThanOrEqual(5);
    for (const d of debates) for (const m of lines(d)) expect(m.content, `${d} ${m.id}`).not.toContain("\n");
    for (const phase of ["opening", "rebuttal", "closing"] as const) {
      for (let i = 0; i < 3; i++) expect(debateLine(phase, "This house would tax sugary drinks", "prop", i).text).not.toContain("\n");
    }
  });

  it("the Amara 1:1 seed has a multi-line reply", () => {
    expect(lines("sessions/ses_seedAmaraHeadache").some((m) => m.content.split("\n").length >= 3)).toBe(true);
  });

  it("chat modes carry breaks but never blank lines", () => {
    for (const d of dirs.filter((x) => read<Session>(`${x}/session.json`).mode !== "debate")) {
      const contents = lines(d).map((m) => m.content);
      expect(contents.some((c) => c.includes("\n")), d).toBe(true);
      for (const c of contents) expect(/\n\n|^\n|\n$/.test(c), `${d}: ${c}`).toBe(false);
    }
    const bank = Object.values(SEED_BANKS).flatMap((b) => b.chat);
    expect(bank.filter((l) => l.text.includes("\n")).length).toBeGreaterThanOrEqual(10);
  });
});
