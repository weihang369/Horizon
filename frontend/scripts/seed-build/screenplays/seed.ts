// The five doc 06 §4 transcripts as screenplays (shipped seed sessions, replay-only, D-47).
import type { Participant, Verdict } from "../../../src/contract/types";
import type { Screenplay } from "../types";

const MERIDIAN = "wld_seedMeridian";
const SUNNY = "wld_seedSunnyHollow";
const P = (characterId: string, extra: Partial<Participant> = {}): Participant => ({
  characterId, role: "speaker", currentEmotion: "neutral", mutedByUser: false, ...extra,
});
const D = (characterId: string, side: "prop" | "opp" | null): Participant => ({
  characterId, role: "debater", side, currentEmotion: "neutral", mutedByUser: false,
});

const AMARA = "chr_seedAmara";
const VICTOR = "chr_seedVictor";
const MEI = "chr_seedMei";
const HANA = "chr_seedHana";
const TAKESHI = "chr_seedTakeshi";
const RIN = "chr_seedRin";

// ── A. 1:1, Amara (AUTO) ─────────────────────────────────────────────────────
export const AMARA_HEADACHE: Screenplay = {
  msgKey: "seedA", evtKey: "seedAmaraHeadache", startAt: "2026-09-29T21:14:00Z", mock: false,
  session: {
    id: "ses_seedAmaraHeadache", worldId: MERIDIAN, title: "Three-day headache", titleIsCustom: false,
    mode: "one_on_one", participants: [P(AMARA)], emotionMode: "llm", musicPolicy: "character_theme",
    readableMode: false, config: null, initialState: null, isSeed: true,
  },
  beats: [
    { k: "line", who: AMARA, emotion: "happy", text: "Shift just ended and I've got tea. What's going on?", gapMs: 200 },
    { k: "user", text: "I've had a headache for three days and coffee isn't helping." },
    {
      k: "line", who: AMARA, emotion: "thinking",
      text: "Three days is long enough that I'd like a bit more detail before guessing. Where is it: behind the eyes, temples, back of the head? And has anything changed lately? Sleep, screen time, how much coffee you usually drink?",
    },
    { k: "user", text: "Temples. And actually I cut back on coffee last week." },
    {
      k: "line", who: AMARA, emotion: "happy", emotionTiming: "early",
      text: "That's a really useful clue. Caffeine withdrawal headaches tend to start a day or so after cutting back and can hang around for several days. They're usually dull and on both sides, like you're describing. Taper rather than stopping cold, keep hydrated, and an over-the-counter painkiller is reasonable if it's safe for you.",
      contextInSession: [{ text: "Kai: temples; cut back on coffee last week", messageId: "msg_seedA04" }],
    },
    { k: "user", text: "Thanks. Anything I should watch out for?" },
    {
      k: "line", who: AMARA, emotion: "neutral",
      text: "Yes, and this is the honest caveat: I can't examine you. If it's suddenly the worst headache of your life, or it comes with fever, a stiff neck, vision changes, confusion or weakness, that's same-day medical care, not a chat with me.",
    },
    { k: "end", status: "paused", reason: "navigated_away" },
  ],
};

// ── B. 1:1, Hana (MANUAL: the user sets the face) ───────────────────────────
export const HANA_LONG_DAY: Screenplay = {
  msgKey: "seedH", evtKey: "seedHanaLongDay", startAt: "2026-09-30T19:02:00Z", mock: false,
  session: {
    id: "ses_seedHanaLongDay", worldId: SUNNY, title: "Long day", titleIsCustom: false,
    mode: "one_on_one", participants: [P(HANA)], emotionMode: "user", musicPolicy: "character_theme",
    readableMode: false, config: null, initialState: null, isSeed: true,
  },
  beats: [
    { k: "face", who: HANA, emotion: "happy" },
    { k: "user", text: "I'm home! Long day." },
    { k: "line", who: HANA, emotion: "happy", text: "Welcome back!! I saved you the last slice of yuzu cake. It's on the counter. Probably. Rin was circling it." },
    { k: "user", text: "You're the best. What did you do today?" },
    { k: "line", who: HANA, emotion: "happy", text: "Oh! A customer ordered fifty sunflowers for a proposal. FIFTY. The whole shop looked like a sunrise." },
    { k: "face", who: HANA, emotion: "embarrassed" },
    { k: "user", text: "…why are you making that face? What happened?" },
    {
      k: "line", who: HANA, emotion: "embarrassed",
      text: "…also, um. I might have sold the bouquet I was making for *you* to that same customer. He looked so nervous! I'll make you another one. With extra ranunculus. Please don't laugh.",
    },
    { k: "end", status: "paused", reason: "navigated_away" },
  ],
};

// ── C. Group: Morisaki dinner (responders: Auto, max 2) ─────────────────────
export const DINNER: Screenplay = {
  msgKey: "seedC", evtKey: "seedDinner", startAt: "2026-09-30T10:30:00Z", mock: false,
  session: {
    id: "ses_seedDinner", worldId: SUNNY, title: "Dinner's on me", titleIsCustom: true,
    mode: "group", participants: [P(HANA), P(TAKESHI), P(RIN)], emotionMode: "llm", musicPolicy: "follow_speaker",
    readableMode: false, config: { responderPolicy: "auto", maxAutoResponders: 2 }, initialState: null, isSeed: true,
  },
  beats: [
    { k: "user", text: "Dinner's on me tonight. What should we order?", gapMs: 300 },
    {
      k: "line", who: TAKESHI, emotion: "happy",
      text: "Sushi. And I'll be honest, I'm only saying that because I've been *fishing* for an invitation.",
      reactions: { [RIN]: "angry", [HANA]: "happy" },
      candidates: [{ characterId: TAKESHI, p: 0.62 }, { characterId: RIN, p: 0.57 }, { characterId: HANA, p: 0.41 }],
    },
    {
      k: "line", who: RIN, emotion: "angry",
      text: "dad. it's 7pm. the puns should be off-duty. pizza. extra pineapple. fight me.",
      reactions: { [TAKESHI]: "surprised", [HANA]: "thinking" },
      candidates: [{ characterId: RIN, p: 0.71 }, { characterId: HANA, p: 0.38 }],
    },
    { k: "user", text: "@Hana break the tie?" },
    {
      k: "line", who: HANA, emotion: "thinking", forcedBy: "mention",
      text: "Compromise? That little place by the station does both… sort of. Their \"fusion roll\" has pineapple in it.",
      reactions: { [RIN]: "surprised", [TAKESHI]: "thinking" },
    },
    { k: "user", text: "@Rin would you actually eat a pineapple sushi roll?" },
    {
      k: "line", who: RIN, emotion: "embarrassed", forcedBy: "mention",
      text: "…i would eat it. i'm not happy about it. but i would eat it.",
      reactions: { [HANA]: "happy", [TAKESHI]: "happy" },
    },
    { k: "end", status: "paused", reason: "navigated_away" },
  ],
};

// ── D. Debate: Meridian Council (two-sided · Standard · moderator You · Arbiter) ──
const RUBRIC = [
  { id: "evidence", label: "Evidence" }, { id: "rebuttal", label: "Rebuttal" },
  { id: "clarity", label: "Clarity" }, { id: "persuasion", label: "Persuasion" },
];

const DEBATE_VERDICT: Verdict = {
  decidedBy: "arbiter",
  strongerCase: "prop",
  scoresBy: "side",
  scores: [
    { subjectId: "prop", criterionId: "evidence", value: 6.5 },
    { subjectId: "prop", criterionId: "rebuttal", value: 7.5 },
    { subjectId: "prop", criterionId: "clarity", value: 8.0 },
    { subjectId: "prop", criterionId: "persuasion", value: 7.5 },
    { subjectId: "opp", criterionId: "evidence", value: 7.5 },
    { subjectId: "opp", criterionId: "rebuttal", value: 7.0 },
    { subjectId: "opp", criterionId: "clarity", value: 8.5 },
    { subjectId: "opp", criterionId: "persuasion", value: 7.0 },
  ],
  summary: [
    { subjectId: "prop", points: [
      "Burnout is itself a staffing cost.",
      "The five-day week is a policy choice, not a law of nature.",
      "Phased legal implementation addresses coverage sectors.",
    ] },
    { subjectId: "opp", points: [
      "Pilot evidence comes from self-selected, easier sectors.",
      "Costs concentrate in health, transport and care.",
      "Fund sector-specific trials before a national mandate.",
    ] },
  ],
  keyDisagreement: "Whether evidence from voluntary pilots generalises to coverage-based sectors.",
  rationale: "Opposition had the stronger evidential framing but conceded direction in closing. Proposition's \"cost of the status quo\" rebuttal went unanswered.",
};

export const DEBATE_4DAY: Screenplay = {
  msgKey: "seedD", evtKey: "seedDebate4Day", startAt: "2026-10-01T09:58:00Z", mock: false,
  session: {
    id: "ses_seedDebate4Day", worldId: MERIDIAN, title: "Debate: Four-day work week", titleIsCustom: false,
    mode: "debate", participants: [D(AMARA, "prop"), D(VICTOR, "prop"), D(MEI, "opp")],
    emotionMode: "llm", musicPolicy: "arena", readableMode: false,
    config: {
      motion: "This house would adopt a nationwide four-day work week.",
      format: "two_sided", sides: { prop: [AMARA, VICTOR], opp: [MEI] }, roundsPreset: "standard",
      phases: ["opening", "rebuttal", "closing"], turnLength: "medium", moderator: "user", verdictBy: "arbiter",
      rubric: RUBRIC, autoAdvance: true, pauseMs: 1500,
    },
    initialState: { phase: "setup", round: 0, iteration: 0 },
    isSeed: true,
  },
  beats: [
    { k: "phase", phase: "opening", round: 1 },
    {
      k: "line", who: AMARA, emotion: "neutral", forcedBy: "round_order", gapMs: 1500,
      text: "I see the downstream cost of chronic overwork every shift: burnout, poor sleep, people arriving at my department with problems that started as exhaustion. A shorter week is a public-health intervention. Pilot programmes have reported lower burnout and better sleep without collapsing output. We should take that signal seriously at national scale.",
      reactions: { [MEI]: "thinking", [VICTOR]: "happy" },
    },
    {
      k: "line", who: MEI, emotion: "thinking", forcedBy: "round_order", gapMs: 1500,
      text: "Nobody here is pro-burnout. My problem is the word *nationwide*. The pilots I've seen were mostly voluntary, self-selected firms, often knowledge work, where output is hard to measure and easy to reorganise. A hospital, a bus network or a care home can't compress five days of coverage into four. They hire more staff or they cut service. Both cost money that somebody pays.",
      reactions: { [AMARA]: "sad", [VICTOR]: "angry" },
    },
    {
      k: "line", who: VICTOR, emotion: "happy", forcedBy: "round_order", gapMs: 1500,
      text: "Three points. One: \"nationwide\" need not mean \"identical\". The motion is about the default standard week, as we once did with the weekend. Two: law already handles continuous-coverage sectors through shift rules. Three: the burden of proof is on the status quo, a five-day week that was itself a policy choice, not a law of nature.",
      reactions: { [MEI]: "surprised", [AMARA]: "happy" },
    },
    { k: "phase", phase: "rebuttal", round: 2 },
    { k: "user", kind: "interject", text: "Concrete numbers this round, please. Everyone.", gapMs: 900 },
    { k: "user", kind: "steer", target: MEI, text: "Mei, give us a number. What does this cost?", gapMs: 1200 },
    {
      // doc 05 §8: this message must match the contract example exactly.
      k: "line", who: MEI, emotion: "thinking", forcedBy: "user_ask", at: "2026-10-01T10:03:14Z",
      text: "Honestly? Nobody can give you one reliable number, and anyone who does is selling something. It depends on how much productivity per hour rises. If it rises enough to offset the lost day, the cost is near zero. If it doesn't, and in coverage-based sectors it mostly can't, you need roughly **a quarter more** staff hours in those sectors to hold service constant. The policy's cost lives entirely in the sectors the pilots didn't test.",
      reactions: { [VICTOR]: "thinking", [AMARA]: "thinking" },
      reactionTiming: { [VICTOR]: { delayMs: 500, p: 0.64 }, [AMARA]: { delayMs: 500, p: 0.58 } },
      usage: { tokensIn: 9800, tokensCached: 7800, tokensOut: 168, costUsd: 0.00042, energySpent: 5, firstTokenMs: 1420, totalMs: 5600 },
      trace: {
        messageId: "msg_seedD08",
        model: {
          id: "deepseek/deepseek-v4.1-flash", provider: "DeepSeek", pricePeriod: "off_peak",
          latencyMs: { firstToken: 1420, total: 5600 }, tokensIn: 9800, tokensCached: 7800, tokensOut: 168, costUsd: 0.00042,
        },
        energy: { characterId: MEI, spent: 5, remaining: 742, max: 1000 },
        emotion: { chosen: "thinking", source: "llm", candidates: [{ label: "thinking", p: 0.71 }, { label: "neutral", p: 0.18 }] },
        routing: { selected: MEI, forcedBy: "user_ask" },
        contextInSession: [{ text: "R1: Mei: pilots were voluntary, self-selected firms", messageId: "msg_seedD03" }],
        context: {
          budget: 12000, cacheHitPct: 80,
          used: { system: 900, persona: 700, memory: 0, knowledge: 0, history: 6900, user: 40, mode: 580 },
        },
      },
    },
    {
      k: "line", who: AMARA, emotion: "angry", forcedBy: "round_order", gapMs: 1500,
      text: "Then count the other side of the ledger too. Exhaustion has its own staffing cost. Burnt-out nurses leave, and every resignation is a recruitment and training bill. \"Hold service constant\" assumes the current service is stable. In my department, it isn't.",
      reactions: { [MEI]: "embarrassed", [VICTOR]: "happy" },
    },
    {
      k: "line", who: VICTOR, emotion: "neutral", forcedBy: "round_order", gapMs: 1500,
      text: "And legally, phase-in is a well-trodden path: sector-by-sector transition periods, collective agreements, public sector first. My learned friend's objection is about *speed*, not *direction*.",
      reactions: { [MEI]: "angry" },
    },
    { k: "phase", phase: "closing", round: 3 },
    {
      k: "line", who: MEI, emotion: "neutral", forcedBy: "round_order", gapMs: 1500,
      text: "I'll concede the direction may be right. But this motion asks for a national mandate based on evidence from the easiest cases. Fund large, sector-specific trials in health, transport and care first. If the numbers hold there, I'll vote with you.",
    },
    {
      k: "line", who: AMARA, emotion: "happy", forcedBy: "round_order", gapMs: 1500,
      text: "That's the most constructive opposition I've heard. But waiting is also a choice, and its cost shows up in my waiting room.",
    },
    {
      k: "line", who: VICTOR, emotion: "happy", forcedBy: "round_order", gapMs: 1500,
      text: "*Res ipsa loquitur*: the thing speaks for itself. Even the Opposition agrees on the destination. We rest.",
    },
    {
      k: "verdict", verdict: DEBATE_VERDICT,
      text: "**Arbiter's assessment** (argument quality, not factual truth)\n\n**Stronger case: Proposition**\n\n**Key disagreement:** whether evidence from voluntary pilots generalises to coverage-based sectors.",
    },
    { k: "end", status: "ended" },
  ],
};

// ── E. Watch: Sunny Hollow ("Rainy Sunday", 10 turns) ───────────────────────
export const RAINY_SUNDAY: Screenplay = {
  msgKey: "seedW", evtKey: "seedRainySunday", startAt: "2026-09-27T02:40:00Z", mock: false,
  session: {
    id: "ses_seedRainySunday", worldId: SUNNY, title: "Rainy Sunday", titleIsCustom: true,
    mode: "watch", participants: [P(TAKESHI), P(RIN)], emotionMode: "llm", musicPolicy: "follow_speaker",
    readableMode: false,
    config: { premise: "Rainy Sunday. Takeshi wants to take Rin fishing; Rin is mid-raid.", maxTurns: 10, paceMs: 1500, openingSpeaker: TAKESHI },
    initialState: { status: "playing", turnsTaken: 0, turnLimit: 10 },
    isSeed: true,
  },
  beats: [
    { k: "line", who: TAKESHI, emotion: "happy", text: "Rain's perfect. Fish bite more when it's grey. Boots on, kiddo." },
    { k: "line", who: RIN, emotion: "neutral", text: "i'm tanking for nine people. if i leave, they wipe. their blood is on your hands." },
    { k: "line", who: TAKESHI, emotion: "thinking", text: "Nine people who've never brought you soup when you had a fever." },
    { k: "line", who: RIN, emotion: "embarrassed", text: "…that's a low blow. accurate. but low." },
    { k: "user", kind: "direction", text: "The rain suddenly stops and the sun comes out.", gapMs: 900 },
    { k: "line", who: TAKESHI, emotion: "surprised", text: "Would you look at that. The sky's on my side." },
    { k: "line", who: RIN, emotion: "angry", text: "the sky is a bot. fine. one hour. and you're carrying the cooler." },
    { k: "line", who: TAKESHI, emotion: "happy", text: "Deal. I'll even let you name the first fish.", reactions: { [RIN]: "happy" } },
    { k: "line", who: RIN, emotion: "thinking", text: "if we catch one, its name is \"Patch Notes\". non-negotiable." },
    { k: "line", who: TAKESHI, emotion: "happy", text: "Patch Notes it is. Your mother would've loved that.", reactions: { [RIN]: "sad" } },
    { k: "line", who: RIN, emotion: "sad", text: "…yeah. she would've. ok. grab the bait, old man.", reactions: { [TAKESHI]: "happy" } },
    { k: "end", status: "paused", reason: "turn_cap" },
  ],
};

export const SEED_SCREENPLAYS: Screenplay[] = [AMARA_HEADACHE, HANA_LONG_DAY, DINNER, DEBATE_4DAY, RAINY_SUNDAY];
