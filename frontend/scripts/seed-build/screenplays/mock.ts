// UI-phase-only sessions (seed/_mock): the debate variants doc 06 §9 requires (panel, auto host, You decide,
// no scores, too close to call) and extra history rows. They are ordinary (non-seed) sessions, so they can be resumed.
import type { DebateConfig, Participant, Verdict } from "../../../src/contract/types";
import type { Beat, Screenplay } from "../types";

const MERIDIAN = "wld_seedMeridian";
const SUNNY = "wld_seedSunnyHollow";
const AMARA = "chr_seedAmara";
const VICTOR = "chr_seedVictor";
const MEI = "chr_seedMei";
const ELENA = "chr_mockElena";
const RIN = "chr_seedRin";

const D = (characterId: string, side: "prop" | "opp" | null): Participant => ({
  characterId, role: "debater", side, currentEmotion: "neutral", mutedByUser: false,
});
const RUBRIC = [
  { id: "evidence", label: "Evidence" }, { id: "rebuttal", label: "Rebuttal" },
  { id: "clarity", label: "Clarity" }, { id: "persuasion", label: "Persuasion" },
];
const quick = (motion: string, extra: Partial<DebateConfig>): DebateConfig => ({
  motion, format: "two_sided", roundsPreset: "quick", phases: ["opening", "closing"], turnLength: "short",
  moderator: "user", verdictBy: "arbiter", rubric: RUBRIC, autoAdvance: true, pauseMs: 1500, ...extra,
});
const sideScores = (prop: number[], opp: number[]) => [
  ...RUBRIC.map((r, i) => ({ subjectId: "prop", criterionId: r.id, value: prop[i] })),
  ...RUBRIC.map((r, i) => ({ subjectId: "opp", criterionId: r.id, value: opp[i] })),
];
const verdictText = (v: Verdict): string => {
  if (v.decidedBy === "none") return "**Summary** (no verdict)";
  const head = v.strongerCase === "prop" ? "Stronger case: Proposition" : v.strongerCase === "opp" ? "Stronger case: Opposition" : "TOO CLOSE TO CALL";
  return `**Arbiter's assessment** (argument quality, not factual truth)\n\n**${head}**${v.keyDisagreement ? `\n\n**Key disagreement:** ${v.keyDisagreement}` : ""}`;
};

// ── Panel: each debater argues their own position; summary-only verdict, no winner ──
const PANEL_VERDICT: Verdict = {
  decidedBy: "arbiter", strongerCase: null,
  summary: [
    { subjectId: AMARA, points: ["Phones fragment sleep and attention; a school-day ban is a cheap public-health win."] },
    { subjectId: VICTOR, points: ["A blanket ban is overbroad; schools already have the power to set reasonable rules."] },
    { subjectId: MEI, points: ["The evidence is mixed; measure outcomes in a staged rollout before banning nationally."] },
  ],
  keyDisagreement: "Whether a national rule or local discretion should decide.",
};
export const PANEL_PHONES: Screenplay = {
  msgKey: "mockP", evtKey: "mockPanelPhones", startAt: "2026-09-24T11:00:00Z", mock: true,
  session: {
    id: "ses_mockPanelPhones", worldId: MERIDIAN, title: "Panel: Phones in schools", titleIsCustom: false,
    mode: "debate", participants: [D(AMARA, null), D(VICTOR, null), D(MEI, null)], emotionMode: "llm", musicPolicy: "arena",
    readableMode: false,
    config: { ...quick("This house would ban smartphones in schools", { format: "panel" }), sides: undefined },
    initialState: { phase: "setup", round: 0, iteration: 0 }, isSeed: false,
  },
  beats: [
    { k: "phase", phase: "opening", round: 1 },
    { k: "line", who: AMARA, emotion: "neutral", forcedBy: "round_order", gapMs: 1500, text: "From the clinic side: teenagers are sleeping less and reporting more anxiety, and phones are part of that story. A school-day ban is cheap, reversible and gives kids six hours a day of protected attention.", reactions: { [MEI]: "thinking" } },
    { k: "line", who: VICTOR, emotion: "thinking", forcedBy: "round_order", gapMs: 1500, text: "Two points. One: schools can already confiscate a disruptive device; a statute adds nothing but rigidity. Two: a national ban invites exceptions for medical and safety use that swallow the rule.", reactions: { [AMARA]: "surprised" } },
    { k: "line", who: MEI, emotion: "thinking", forcedBy: "round_order", gapMs: 1500, text: "The studies people quote are small and mostly correlational. I'd stage it: let some districts ban, measure grades and wellbeing, then decide. It depends, and here's on what: enforcement.", reactions: { [VICTOR]: "happy" } },
    { k: "phase", phase: "closing", round: 2 },
    { k: "line", who: AMARA, emotion: "happy", forcedBy: "round_order", gapMs: 1500, text: "I'd take a staged rollout over nothing. Just don't let \"more data\" become \"never\"." },
    { k: "line", who: VICTOR, emotion: "neutral", forcedBy: "round_order", gapMs: 1500, text: "Local rules, clearly drafted, beat a national blunt instrument. The panel rests." },
    { k: "line", who: MEI, emotion: "neutral", forcedBy: "round_order", gapMs: 1500, text: "Pilot, measure, publish. Then argue." },
    { k: "verdict", verdict: PANEL_VERDICT, text: "**Panel summary** (no winner in panel format)" },
    { k: "end", status: "ended" },
  ],
};

// ── Auto host: an AI host voices the transitions ──
const HOST_VERDICT: Verdict = {
  decidedBy: "arbiter", strongerCase: "prop", scoresBy: "side",
  scores: sideScores([7.5, 7.0, 8.0, 7.5], [6.5, 7.0, 7.5, 6.5]),
  summary: [
    { subjectId: "prop", points: ["Sugar taxes shift purchases measurably.", "Revenue can fund school meals."] },
    { subjectId: "opp", points: ["Regressive for low-income households.", "Industry reformulates around thresholds."] },
  ],
  keyDisagreement: "Whether regressivity is outweighed by health gains.",
  rationale: "Proposition answered the regressivity point with earmarked revenue; Opposition did not rebut it.",
};
export const HOST_SUGAR: Screenplay = {
  msgKey: "mockS", evtKey: "mockHostSugar", startAt: "2026-09-22T13:20:00Z", mock: true,
  session: {
    id: "ses_mockHostSugar", worldId: MERIDIAN, title: "Debate: Sugar tax (auto host)", titleIsCustom: false,
    mode: "debate", participants: [D(AMARA, "prop"), D(VICTOR, "opp")], emotionMode: "llm", musicPolicy: "arena",
    readableMode: false,
    config: quick("This house would tax sugary drinks", { sides: { prop: [AMARA], opp: [VICTOR] }, moderator: "auto_host" }),
    initialState: { phase: "setup", round: 0, iteration: 0 }, isSeed: false,
  },
  beats: [
    { k: "host", text: "Welcome to the Meridian Council. Tonight's motion: this house would tax sugary drinks. Dr. Okafor opens for the Proposition." },
    { k: "phase", phase: "opening", round: 1 },
    { k: "line", who: AMARA, emotion: "neutral", forcedBy: "round_order", gapMs: 1200, text: "Where sugar taxes exist, purchases of taxed drinks fall, and the revenue can be earmarked for school meals. It's one of the few nutrition policies with a clear signal.", reactions: { [VICTOR]: "thinking" } },
    { k: "host", text: "Thank you. Mr. Hale, for the Opposition." },
    { k: "line", who: VICTOR, emotion: "angry", forcedBy: "round_order", gapMs: 1200, text: "Three points. It's regressive. It's paternalistic. And manufacturers simply reformulate to sit a gram under the threshold. You tax the poor and change the label.", reactions: { [AMARA]: "surprised" } },
    { k: "host", text: "Closing statements. Proposition first." },
    { k: "phase", phase: "closing", round: 2 },
    { k: "line", who: AMARA, emotion: "happy", forcedBy: "round_order", gapMs: 1200, text: "Reformulation is the point. Less sugar in the bottle is a win, whoever drinks it." },
    { k: "line", who: VICTOR, emotion: "neutral", forcedBy: "round_order", gapMs: 1200, text: "A win bought from the poorest wallets. The Opposition rests." },
    { k: "host", text: "The arbiter will now assess the arguments." },
    { k: "verdict", verdict: HOST_VERDICT, text: verdictText(HOST_VERDICT) },
    { k: "end", status: "ended" },
  ],
};

// ── You decide: summary first, then the user picks the stronger side (D-48). Left waiting for the pick. ──
export const YOU_DECIDE_VOTING: Screenplay = {
  msgKey: "mockV", evtKey: "mockYouDecideVoting", startAt: "2026-09-25T15:05:00Z", mock: true,
  session: {
    id: "ses_mockYouDecideVoting", worldId: MERIDIAN, title: "Debate: Compulsory voting", titleIsCustom: false,
    mode: "debate", participants: [D(VICTOR, "prop"), D(MEI, "opp")], emotionMode: "llm", musicPolicy: "arena",
    readableMode: false,
    config: quick("This house would make voting compulsory", { sides: { prop: [VICTOR], opp: [MEI] }, verdictBy: "user" }),
    initialState: { phase: "setup", round: 0, iteration: 0 }, isSeed: false,
  },
  beats: [
    { k: "phase", phase: "opening", round: 1 },
    { k: "line", who: VICTOR, emotion: "happy", forcedBy: "round_order", gapMs: 1500, text: "Australia has compelled turnout for a century without tyranny. A duty to show up, with a box for \"none of the above\", is the cheapest legitimacy upgrade a democracy can buy.", reactions: { [MEI]: "thinking" } },
    { k: "line", who: MEI, emotion: "thinking", forcedBy: "round_order", gapMs: 1500, text: "Turnout goes up, sure. Informed turnout is a different variable. You'd raise the count and maybe lower the signal.", reactions: { [VICTOR]: "surprised" } },
    { k: "phase", phase: "closing", round: 2 },
    { k: "line", who: VICTOR, emotion: "neutral", forcedBy: "round_order", gapMs: 1500, text: "Signal improves when politicians must court everyone, not just the reliable voters." },
    { k: "line", who: MEI, emotion: "neutral", forcedBy: "round_order", gapMs: 1500, text: "Or campaigns get louder and dumber. The evidence on that is honestly thin." },
    { k: "phase", phase: "verdict", round: 3, label: "VERDICT · YOUR CALL" },
    { k: "end", status: "paused", reason: "user" },
  ],
};

// ── Arbiter with no scores (bars hidden, summary alone) ──
const NO_SCORES_VERDICT: Verdict = {
  decidedBy: "arbiter", strongerCase: "opp",
  summary: [
    { subjectId: "prop", points: ["Remote work erodes mentoring for juniors."] },
    { subjectId: "opp", points: ["Productivity data favours hybrid work.", "Commute time returned to workers is a real gain."] },
  ],
  keyDisagreement: "Whether mentoring losses outweigh productivity gains.",
};
export const NO_SCORES_REMOTE: Screenplay = {
  msgKey: "mockN", evtKey: "mockNoScoresRemote", startAt: "2026-09-20T10:10:00Z", mock: true,
  session: {
    id: "ses_mockNoScoresRemote", worldId: MERIDIAN, title: "Debate: Remote work", titleIsCustom: false,
    mode: "debate", participants: [D(VICTOR, "prop"), D(MEI, "opp")], emotionMode: "llm", musicPolicy: "arena",
    readableMode: false,
    config: quick("This house believes remote work does more harm than good", { sides: { prop: [VICTOR], opp: [MEI] } }),
    initialState: { phase: "setup", round: 0, iteration: 0 }, isSeed: false,
  },
  beats: [
    { k: "phase", phase: "opening", round: 1 },
    { k: "line", who: VICTOR, emotion: "neutral", forcedBy: "round_order", gapMs: 1500, text: "Juniors learn by overhearing. Remote work deletes the overhearing. That is the whole case, and it is sufficient." },
    { k: "line", who: MEI, emotion: "happy", forcedBy: "round_order", gapMs: 1500, text: "Hybrid teams in the better studies hold productivity and lose less staff. Mentoring can be scheduled; commutes can't be refunded." },
    { k: "phase", phase: "closing", round: 2 },
    { k: "line", who: VICTOR, emotion: "thinking", forcedBy: "round_order", gapMs: 1500, text: "Scheduled mentoring is a meeting, not an apprenticeship." },
    { k: "line", who: MEI, emotion: "neutral", forcedBy: "round_order", gapMs: 1500, text: "Then fix the apprenticeship, not the postcode." },
    { k: "verdict", verdict: NO_SCORES_VERDICT, text: verdictText(NO_SCORES_VERDICT) },
    { k: "end", status: "ended" },
  ],
};

// ── Too close to call (strongerCase null in two-sided mode) ──
const TOO_CLOSE_VERDICT: Verdict = {
  decidedBy: "arbiter", strongerCase: null, scoresBy: "side",
  scores: sideScores([7.0, 7.5, 7.0, 7.5], [7.5, 7.0, 7.5, 7.0]),
  summary: [
    { subjectId: "prop", points: ["Exams reward cramming, not understanding.", "Continuous assessment catches struggling students earlier."] },
    { subjectId: "opp", points: ["Coursework is easier to game.", "Exams are the fairest single snapshot we have."] },
  ],
  keyDisagreement: "Which method is harder to game.",
  rationale: "Both sides landed their main point and neither rebuttal was decisive.",
};
export const TOO_CLOSE_EXAMS: Screenplay = {
  msgKey: "mockT", evtKey: "mockTooCloseExams", startAt: "2026-09-18T16:45:00Z", mock: true,
  session: {
    id: "ses_mockTooCloseExams", worldId: MERIDIAN, title: "Debate: Exams vs coursework", titleIsCustom: false,
    mode: "debate", participants: [D(ELENA, "prop"), D(AMARA, "prop"), D(MEI, "opp")], emotionMode: "llm", musicPolicy: "arena",
    readableMode: false,
    config: quick("This house would replace exams with continuous assessment", { sides: { prop: [ELENA, AMARA], opp: [MEI] } }),
    initialState: { phase: "setup", round: 0, iteration: 0 }, isSeed: false,
  },
  beats: [
    { k: "phase", phase: "opening", round: 1 },
    { k: "line", who: ELENA, emotion: "neutral", forcedBy: "round_order", gapMs: 1500, text: "I taught for twelve years. The exam measured who slept well the night before. Coursework measured who learned.", reactions: { [MEI]: "thinking" } },
    { k: "line", who: MEI, emotion: "thinking", forcedBy: "round_order", gapMs: 1500, text: "Coursework measures who has a parent with a printer and an evening free. The exam is crude, but it's the same crude for everyone." },
    { k: "line", who: AMARA, emotion: "happy", forcedBy: "round_order", gapMs: 1500, text: "Continuous assessment also flags the kid who's struggling in October, not in June when it's too late." },
    { k: "phase", phase: "closing", round: 2 },
    { k: "line", who: ELENA, emotion: "happy", forcedBy: "round_order", gapMs: 1500, text: "Learning is continuous. Assessment should rhyme with it." },
    { k: "line", who: MEI, emotion: "neutral", forcedBy: "round_order", gapMs: 1500, text: "Fairness is a snapshot. I'll take the snapshot." },
    { k: "line", who: AMARA, emotion: "neutral", forcedBy: "round_order", gapMs: 1500, text: "Then take two snapshots and a conversation. We rest." },
    { k: "verdict", verdict: TOO_CLOSE_VERDICT, text: verdictText(TOO_CLOSE_VERDICT) },
    { k: "end", status: "ended" },
  ],
};

// ── Extra history row in Sunny Hollow: a short 1:1 with Rin (resumable) ──
const rinBeats: Beat[] = [
  { k: "line", who: RIN, emotion: "neutral", text: "oh. it's you. hi. (that was a warm greeting btw)", gapMs: 200 },
  { k: "user", text: "Raid tonight?" },
  { k: "line", who: RIN, emotion: "happy", text: "obviously. 9pm. if you queue as healer i will personally carry you. once." },
  { k: "user", text: "Deal. Don't tell Hana I'm skipping dinner." },
  { k: "line", who: RIN, emotion: "embarrassed", text: "…i'm not a snitch. i'm a *strategic informant*. fine. our secret." },
  { k: "end", status: "paused", reason: "navigated_away" },
];
export const RIN_RAID: Screenplay = {
  msgKey: "mockR", evtKey: "mockRinRaid", startAt: "2026-09-26T12:15:00Z", mock: true,
  session: {
    id: "ses_mockRinRaid", worldId: SUNNY, title: "Raid night", titleIsCustom: false,
    mode: "one_on_one", participants: [{ characterId: RIN, role: "speaker", currentEmotion: "neutral", mutedByUser: false }],
    emotionMode: "llm", musicPolicy: "character_theme", readableMode: false, config: null, initialState: null, isSeed: false,
  },
  beats: rinBeats,
};

export const MOCK_SCREENPLAYS: Screenplay[] = [PANEL_PHONES, HOST_SUGAR, YOU_DECIDE_VOTING, NO_SCORES_REMOTE, TOO_CLOSE_EXAMS, RIN_RAID];
