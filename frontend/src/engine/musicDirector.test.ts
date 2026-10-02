// musicDirector (MUS-01..08). Owner: EE.
import { describe, expect, it } from "vitest";
import type { MusicCast, MusicInput } from "./musicDirector";
import { FOLLOW_DWELL_MS, musicDirector } from "./musicDirector";

const theme = (id: string) => ({ url: `/t/${id}`, label: `${id}'s Theme`, characterId: id });
const system = { main: { url: "/sys/main", label: "Main" }, arena: { url: "/sys/arena", label: "Arena" }, ambient: { url: "/sys/bed", label: "Bed" } };
const cast: MusicCast[] = [
  { characterId: "a", name: "A", side: "prop", theme: theme("a") },
  { characterId: "b", name: "B", side: "opp", theme: theme("b") },
  { characterId: "c", name: "C", side: "opp", theme: null },
];
const base = (over: Partial<MusicInput>): MusicInput => ({ mode: "group", cast, system, ...over });

describe("musicDirector", () => {
  it("hub plays the main theme; 1:1 plays the character theme or the ambient bed (MUS-07)", () => {
    expect(musicDirector(base({ mode: "hub" }), 0).track?.url).toBe("/sys/main");
    expect(musicDirector(base({ mode: "one_on_one", cast: [cast[0]] }), 0).track?.url).toBe("/t/a");
    expect(musicDirector(base({ mode: "one_on_one", cast: [cast[2]] }), 0).track?.url).toBe("/sys/bed");
  });

  it("debate plays Arena until a verdict, then the winning side's theme; too close keeps Arena", () => {
    expect(musicDirector(base({ mode: "debate", policy: "arena" }), 0).track?.url).toBe("/sys/arena");
    const won = musicDirector(base({ mode: "debate", verdict: { decidedBy: "arbiter", strongerCase: "opp", summary: [] } }), 0);
    expect(won.track?.url).toBe("/t/b");
    const tie = musicDirector(base({ mode: "debate", verdict: { decidedBy: "arbiter", strongerCase: null, summary: [] } }), 0);
    expect(tie.track?.url).toBe("/sys/arena");
  });

  it("follow-speaker holds the current track for the 20 s dwell", () => {
    const now = 100_000;
    const held = musicDirector(base({ policy: "follow_speaker", speakerId: "b", current: { url: "/t/a", since: now - 5_000 } }), now);
    expect(held.track?.url).toBe("/t/a");
    expect(held.heldByDwell).toBe(true);
    const moved = musicDirector(base({ policy: "follow_speaker", speakerId: "b", current: { url: "/t/a", since: now - FOLLOW_DWELL_MS - 1 } }), now);
    expect(moved.track?.url).toBe("/t/b");
    const silentSpeaker = musicDirector(base({ policy: "follow_speaker", speakerId: "c", current: { url: "/t/a", since: 0 } }), now);
    expect(silentSpeaker.track?.url).toBe("/t/a");
  });

  it("scene bed policy plays the ambient bed", () => {
    expect(musicDirector(base({ mode: "watch", policy: "scene_bed" }), 0).track?.url).toBe("/sys/bed");
  });
});
