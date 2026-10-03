// D-59 seed knowledge: sources + indexed passages (chunks). All fictional: Meridian and Sunny Hollow only.
// Chunks are written to seed/knowledge/chunks/<sourceId>.json; citedCount is computed from the compiled sessions.
import type { KnowledgeChunk, KnowledgeSource } from "../../../src/contract/types";

const MERIDIAN = "wld_seedMeridian";
const SUNNY = "wld_seedSunnyHollow";

export const KNOWLEDGE_SOURCES: KnowledgeSource[] = [
  {
    id: "kno_seedAmara1", characterId: "chr_seedAmara", worldId: MERIDIAN, title: "Meridian Shift Fatigue Review 2025.pdf",
    type: "file", status: "indexed", bytes: 482_113, pages: 18, addedAt: "2026-09-18T08:40:00Z",
  },
  {
    id: "kno_seedAmara2", characterId: "chr_seedAmara", worldId: MERIDIAN, title: "ED triage guidelines",
    type: "url", status: "indexed", url: "https://meridian-health.example/ed/triage-guidelines", addedAt: "2026-09-21T19:12:00Z",
  },
  {
    id: "kno_seedMei1", characterId: "chr_seedMei", worldId: MERIDIAN, title: "Working-time pilots dataset.csv",
    type: "file", status: "failed", bytes: 2_310_442, addedAt: "2026-09-24T14:05:00Z",
    error: "Couldn't read this file: row 4,118 has 31 columns, expected 27. Fix the row or export the sheet again.",
  },
  {
    id: "kno_seedMei2", characterId: "chr_seedMei", worldId: MERIDIAN, title: "Four-day week pilot summaries.pdf",
    type: "file", status: "indexed", bytes: 1_204_660, pages: 24, addedAt: "2026-09-24T14:11:00Z",
  },
  {
    id: "kno_seedVictor1", characterId: "chr_seedVictor", worldId: MERIDIAN, title: "Moot court notes",
    type: "text", status: "indexed", bytes: 18_220, addedAt: "2026-09-22T22:30:00Z",
  },
  {
    id: "kno_seedHana1", characterId: "chr_seedHana", worldId: SUNNY, title: "Grandma's recipe notebook",
    type: "text", status: "indexed", bytes: 6_480, addedAt: "2026-09-15T16:20:00Z",
  },
];

type Passage = [locator: string, text: string];

const PASSAGES: Record<string, { key: string; passages: Passage[] }> = {
  kno_seedAmara1: { key: "amaraFat", passages: [
    ["p. 2", "This review covers 1,140 clinical staff across four Meridian Health Trust sites between January and October 2025. Fatigue was measured with a fortnightly self-report scale and matched against rota data. All names and units are anonymised."],
    ["p. 3", "Staff working more than three consecutive long shifts reported fatigue scores 38% higher than colleagues on shorter blocks. The effect was strongest in emergency and acute medicine, where rest days were most often cancelled at short notice."],
    ["p. 4", "Self-reported burnout rose in every quarter of the review period. By October, 41% of emergency department staff met the review's threshold for high burnout, up from 29% in January."],
    ["p. 6", "Poor sleep was the most common complaint, named by 63% of respondents. Staff who slept under six hours before a shift were twice as likely to report a near-miss medication error that week."],
    ["p. 7", "Fatigue-related problems among staff themselves, from headaches and gastric complaints to minor injuries on the commute home, cost the Trust an estimated 2,300 lost shifts."],
    ["p. 9", "Two wards piloted a compressed rota: four longer days, then three days off. After twelve weeks, burnout scores on both wards fell by roughly a fifth, sleep quality improved, and patient throughput stayed within normal variation."],
    ["p. 11", "The pilot wards needed 6% more agency hours during the transition month to cover handovers. That cost fell back to baseline by week eight, once teams had settled the new handover pattern."],
    ["p. 13", "Voluntary resignations among nursing staff reached 14% over the year. The Trust's finance office puts each replacement at roughly four months of salary once recruitment, induction and supervised practice are counted."],
    ["p. 15", "Exit interviews named workload and unpredictable rotas as the two leading reasons for leaving, ahead of pay. Several leavers said they would have stayed for a guaranteed rest pattern."],
    ["p. 17", "The review recommends extending the compressed-rota pilot to three further departments, protecting rest days from short-notice cancellation, and reporting fatigue scores to the Trust board every quarter."],
  ] },
  kno_seedAmara2: { key: "amaraTri", passages: [
    ["§ 1.2", "Triage assigns urgency, not diagnosis. Nurses grade each presentation from 1 (immediate) to 5 (non-urgent) using the presenting complaint and the observations taken on arrival."],
    ["§ 2.1", "Most headaches seen in the department are primary headaches: tension-type, migraine, or medication- and caffeine-related. A dull, pressing pain on both sides without neurological signs is typical of tension-type or withdrawal headache."],
    ["§ 2.4", "Caffeine withdrawal headache usually begins 12 to 24 hours after a sharp cut in intake and can last two to nine days. Gradual tapering, fluids and simple painkillers are usually enough; it rarely needs emergency care."],
    ["§ 3.1", "Escalate any headache that is sudden and severe (\"thunderclap\"), or that comes with fever, neck stiffness, confusion, new weakness or changes in vision. These patients are graded 2 or higher and seen by a doctor without delay."],
    ["§ 3.3", "A first severe headache after age 50, a headache after a head injury, or one that wakes the patient from sleep should also be reviewed the same day, even when observations are normal."],
    ["§ 4.2", "Advice given by phone or chat must say clearly that it is not an examination. Tell the patient which symptoms mean they should come in person."],
  ] },
  kno_seedMei2: { key: "meiPilot", passages: [
    ["p. 1", "This compendium summarises fourteen four-day week pilots run in Meridian between 2023 and 2025, covering 212 organisations and about 9,800 workers. Every participating organisation volunteered."],
    ["p. 3", "Seventy-one percent of participating organisations were in professional services, software, marketing or the non-profit sector. Only nine provided round-the-clock or shift-based services."],
    ["p. 5", "Across all pilots, self-reported burnout fell by an average of 32% and sick days by 21%. Revenue stayed broadly flat, but fewer than half of the firms tracked output with a consistent measure."],
    ["p. 7", "Firms with the biggest gains had halved their meetings and redesigned workflows before the trial began. Firms that simply removed a day without redesign saw smaller benefits and more overtime."],
    ["p. 9", "None of the pilots included an acute hospital, a public transport operator or a residential care provider. The authors flag this as the main gap in the evidence."],
    ["p. 12", "In the nine shift-based organisations, holding coverage constant took between 18% and 27% more staffed hours, met through new hires, overtime or agency workers."],
    ["p. 14", "Ninety-two percent of organisations kept the four-day week after the pilot. Participants were not randomly selected, so the authors warn against reading this as a national estimate."],
    ["p. 17", "Worker retention improved in most pilots: voluntary resignations fell from 6.1% to 4.3% on average over the trial period."],
    ["p. 20", "The authors recommend sector-specific trials in health, transport and care, with independent measurement of output and service quality, before any national standard is set."],
    ["p. 22", "Results come from employee surveys at the start, midpoint and end of each pilot, alongside finance data reported by each organisation. Survey response fell from 74% to 58% by the final wave."],
  ] },
  kno_seedVictor1: { key: "victorMoot", passages: [
    ["¶ 1", "Expect the opposition to say the evidence base is narrow. Concede scope early, then shift the burden: the status quo is also a policy and has to justify itself."],
    ["¶ 2", "Historical anchor: the Meridian Working Hours Act 1931 made the two-day weekend the default. It gave agriculture and shipping a ten-year transition and exempted continuous services."],
    ["¶ 3", "Continuous-coverage sectors already run on shift rules under Part IV of the Working Time Code: rest periods, a cap on consecutive shifts, and averaging over a reference period. A shorter standard week sits inside that structure."],
    ["¶ 4", "Phase-in precedent: sector-by-sector timetables, collective agreements first, the public sector as model employer. Courts have upheld staged duties where the end point is clear."],
    ["¶ 5", "Watch for the \"speed, not direction\" turn. Once the opposition accepts the goal, the debate is about implementation, and the side with a timetable wins it."],
    ["¶ 6", "Closing options: res ipsa loquitur; \"the destination is agreed\". Don't sound triumphant. Judges reward conceding a fair point gracefully."],
  ] },
  kno_seedHana1: { key: "hanaRecipe", passages: [
    ["p. 2", "Yuzu cake: zest two yuzu into the sugar first and rub it with your fingers until it smells like winter sunshine. Don't skip this. The juice goes in the glaze, never the batter."],
    ["p. 5", "Sushi rice for a crowd: three cups of rice and a splash more vinegar than you think. A spoon of pineapple juice in the vinegar keeps it bright when the fish is rich. Your grandfather never noticed."],
    ["p. 8", "Rainy-day soup: miso, tofu and whatever greens are wilting. If a child refuses it, call it \"dragon broth\" and serve it in the good bowls."],
    ["p. 11", "Flowers on the table should never be taller than your elbow. People want to see each other when they eat."],
    ["p. 14", "Leftover rice becomes tomorrow's onigiri. Salt your hands, not the rice, and press as if you were holding a small bird."],
  ] },
};

const pad2 = (n: number) => String(n).padStart(2, "0");

/** Chunks by source id, ordered. Ids: kch_<key><nn>. */
export const KNOWLEDGE_CHUNKS: Record<string, KnowledgeChunk[]> = Object.fromEntries(
  Object.entries(PASSAGES).map(([sourceId, { key, passages }]) => [
    sourceId,
    passages.map(([locator, text], i) => ({ id: `kch_${key}${pad2(i + 1)}`, sourceId, index: i, locator, text })),
  ]),
);

export const CHUNK_BY_ID: Record<string, { chunk: KnowledgeChunk; source: KnowledgeSource }> = Object.fromEntries(
  Object.values(KNOWLEDGE_CHUNKS).flat().map((chunk) => [
    chunk.id, { chunk, source: KNOWLEDGE_SOURCES.find((s) => s.id === chunk.sourceId)! },
  ]),
);
