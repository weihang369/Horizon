import { describe, expect, it } from "vitest";
import { edgeFade, FADE_IN_SEC, FADE_OUT_SEC } from "./edges";

const RATE = 100;

describe("theme edge fades (v1 review U-01)", () => {
  it("trims silent edges, then fades in from silence and out to silence", () => {
    const tone = new Float32Array(10 + 30 * RATE + 20).fill(0.5);
    tone.fill(0, 0, 10);
    tone.fill(0, tone.length - 20);
    const [d] = edgeFade([tone], RATE);
    expect(d.length).toBe(30 * RATE);
    expect(d[0]).toBe(0);
    expect(d[Math.round(FADE_IN_SEC * RATE) / 2]).toBeGreaterThan(0.3);
    expect(d[Math.round(FADE_IN_SEC * RATE) / 2]).toBeLessThan(0.5);
    expect(d[15 * RATE]).toBe(0.5);
    expect(d[d.length - 1]).toBe(0);
    expect(d[d.length - 1 - Math.round(FADE_OUT_SEC * RATE) / 2]).toBeLessThan(0.5);
  });

  it("trims every channel the same and caps each fade at a quarter of a short clip", () => {
    const left = new Float32Array(400).fill(0.5);
    const right = new Float32Array(400).fill(0.5);
    left.fill(0, 0, 100);   // the right channel is loud from the start, so nothing is trimmed
    const [l, r] = edgeFade([left, right], RATE);
    expect(l.length).toBe(400);
    expect(r.length).toBe(400);
    expect(r[100]).toBe(0.5);   // a quarter (100 samples) of fade-in, then full level
  });

  it("leaves a silent clip alone", () => {
    const silent = [new Float32Array(50)];
    expect(edgeFade(silent, RATE)).toBe(silent);
  });
});
