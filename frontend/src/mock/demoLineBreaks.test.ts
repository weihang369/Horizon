// Demo parity for bubbles (D-46; ai-foundation design D22; task 4.3): chat-mode character lines in the recorded
// sessions and the mock banks may hold line breaks (shown as up to 4 bubbles); debate lines never do. The recorded
// replies also hold blank lines (the model writes paragraphs); splitBubbles collapses them, so no bubble is empty.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import type { Message, Session } from "../contract/types";
import { debateLine } from "./banks/generic";
import { SEED_BANKS } from "./banks/seedBanks";
import { splitBubbles } from "../features/session/bubbles";

const SEED = path.resolve(__dirname, "../../../seed");
const dirs = ["sessions", "_mock/sessions"].flatMap((d) => (existsSync(path.join(SEED, d)) ? readdirSync(path.join(SEED, d)).map((s) => `${d}/${s}`) : []));
const read = <T,>(rel: string) => (JSON.parse(readFileSync(path.join(SEED, rel), "utf8")) as { data: T }).data;
const lines = (dir: string) => read<Message[]>(`${dir}/messages.json`).filter((m) => m.author.type === "character");

describe("demo line breaks", () => {
  it("debate messages are paragraphs: no single line breaks (a recorded reply may still hold a paragraph break)", () => {
    const debates = dirs.filter((d) => read<Session>(`${d}/session.json`).mode === "debate");
    expect(debates.length).toBeGreaterThanOrEqual(4);   // the four-day debate + three mock debates (D-117)
    // The prompt asks for one paragraph; the real model wrote two on 1 of 10 turns of the recorded debate (2026-10-21).
    for (const d of debates) for (const m of lines(d)) expect(m.content.replace(/\n\n/g, ""), `${d} ${m.id}`).not.toContain("\n");
    for (const phase of ["opening", "rebuttal", "closing"] as const) {
      for (let i = 0; i < 3; i++) expect(debateLine(phase, "This house would tax sugary drinks", "prop", i).text).not.toContain("\n");
    }
  });

  it("the Amara 1:1 seed has a multi-line reply", () => {
    expect(lines("sessions/ses_seedAmaraHeadache").some((m) => m.content.split("\n").length >= 3)).toBe(true);
  });

  it("chat modes carry breaks, and blank lines never make an empty bubble", () => {
    const chats = dirs.filter((x) => read<Session>(`${x}/session.json`).mode !== "debate");
    // Recorded replies: the model chooses the breaks, so most (not every) chat session shows several bubbles.
    expect(chats.filter((d) => lines(d).some((m) => m.content.includes("\n"))).length).toBeGreaterThanOrEqual(chats.length - 1);
    for (const d of chats) {
      const contents = lines(d).map((m) => m.content);
      for (const c of contents) {
        expect(/^\s|\s$/.test(c), `${d}: ${c}`).toBe(false);
        for (const b of splitBubbles(c)) expect(b.trim(), `${d}: ${c}`).not.toBe("");
      }
    }
    const bank = Object.values(SEED_BANKS).flatMap((b) => b.chat);
    expect(bank.filter((l) => l.text.includes("\n")).length).toBeGreaterThanOrEqual(10);
  });
});
