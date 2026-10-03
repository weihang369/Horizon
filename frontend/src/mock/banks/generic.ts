// Generic bank: templates over a character's profile (wizard-made characters), plus debate and scene templates.
// Owner: EE.
import type { Character, DebateTurnPhase, Side } from "../../contract/types";
import type { BankLine } from "./types";

const first = (c: Character) => c.profile.name.split(" ").find((w) => !/^(dr|prof|mr|ms|mrs)\.?$/i.test(w)) ?? c.profile.name;

export function genericChat(c: Character): BankLine[] {
  const p = c.profile;
  const quip = p.speakingStyle.catchphrases[0];
  const field = p.expertise[0] ?? p.role.toLowerCase();
  return [
    { text: p.greeting || `Hi, I'm ${first(c)}. What's on your mind?`, emotion: "happy", tags: ["hi", "hello", "hey"] },
    { text: `As a ${p.role.toLowerCase()}, I'd start with one question: what does a good outcome look like for you?`, emotion: "thinking", tags: ["help", "should", "how", "what"] },
    { text: `${p.tagline} At least, that's how I see it.`, emotion: "neutral" },
    { text: `Oh, that's interesting. In ${field}, that almost never goes the way people expect.`, emotion: "surprised", tags: ["think", "idea", "maybe"] },
    { text: quip ? `${quip} Sorry, I had to.` : "Ha, okay, you got me there.", emotion: "embarrassed" },
    { text: "Hmm. I don't love that. Tell me why you think it's the right call?", emotion: "thinking", tags: ["but", "why", "because"] },
    { text: "That's genuinely good news. Tell me more!", emotion: "happy", tags: ["great", "good", "done", "passed", "thanks"] },
    { text: "That sounds hard. I'm listening, take your time.", emotion: "sad", tags: ["sad", "bad", "tired", "stress", "worried"] },
  ];
}

const PHASE_LINES: Record<DebateTurnPhase, ((motion: string, side: string) => BankLine)[]> = {
  opening: [
    (m, s) => ({ text: `Let me set out the ${s} case plainly. "${m}" is not a slogan; it is a trade-off, and the benefits are larger than the costs.`, emotion: "neutral" }),
    (_m, s) => ({ text: `Three things decide this motion: who pays, who benefits, and how fast it can be undone. On all three, the ${s} side holds.`, emotion: "thinking" }),
    (m) => ({ text: `Before anyone gets carried away: "${m}" sounds simple. The evidence for it is narrower than its supporters admit.`, emotion: "thinking" }),
  ],
  rebuttal: [
    (_m, s) => ({ text: `My opponents describe the best case and call it the expected case. The ${s} position simply asks what happens on an ordinary Tuesday.`, emotion: "angry" }),
    () => ({ text: "That example was vivid, I'll give it that. But a vivid example is not a representative one.", emotion: "thinking" }),
    () => ({ text: "Honestly? I agree with half of that. It's the other half that sinks the argument.", emotion: "surprised" }),
  ],
  closing: [
    (m, s) => ({ text: `So where are we? The ${s} side has shown its costs are real and measurable. Weigh that before you accept "${m}".`, emotion: "neutral" }),
    () => ({ text: "Strip away the rhetoric and one question is left: who carries the risk if we're wrong? Answer that, and you have your verdict.", emotion: "thinking" }),
    () => ({ text: "I came in sceptical and I leave sceptical, but better informed. That's the most honest closing I can give.", emotion: "happy" }),
  ],
};

export function debateLine(phase: DebateTurnPhase, motion: string, side: Side | null | undefined, index: number): BankLine {
  const sideLabel = side === "prop" ? "proposition" : side === "opp" ? "opposition" : "panel";
  const lines = PHASE_LINES[phase];
  return lines[index % lines.length](motion.replace(/^this house (would|believes)\s*/i, ""), sideLabel);
}

export function answerTo(question: string): BankLine {
  return { text: `You asked: "${question.slice(0, 80)}". Direct answer: it depends on the assumptions, and I'll name mine so you can attack them.`, emotion: "thinking" };
}

export function sceneLines(c: Character, premise: string): BankLine[] {
  return [
    { text: `${premise.split(".")[0]}. Of course this would happen today.`, emotion: "neutral" },
    { text: "Well, nobody told me there'd be a plot twist.", emotion: "surprised" },
    { text: `${first(c)} sighs. Fine. Let's see where this goes.`, emotion: "thinking" },
    { text: "Okay, that was actually kind of nice.", emotion: "happy" },
  ];
}

export function directionLines(note: string): BankLine[] {
  const n = note.replace(/\.$/, "").toLowerCase();
  return [
    { text: `Wait, ${n}? That changes everything.`, emotion: "surprised" },
    { text: `Huh. ${note} I didn't see that coming.`, emotion: "thinking" },
    { text: `Of course ${n}. Of course it does.`, emotion: "angry" },
  ];
}
