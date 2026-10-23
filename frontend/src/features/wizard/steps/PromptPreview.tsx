// CHR-05 "View as prompt" (docs/ai/04 P10; persona-prompt "The preview is the real prompt"): the real `agent` system
// message for a 1:1 chat in this world, compiled by the backend compiler's TS twin, with the backend's token count
// and a note on anything P4's limit shortened or left out. (M9's mood-line note, D17, went with the line's
// default, D40: replies no longer carry one.) M10 (group-watch D10): one fixed note under the message says a group or
// watch reply's cue may add a sentence, with an example from the same table the backend uses. M11 (debate D10): a
// second fixed note quotes the debate cue table's rebuttal line.
import { useMemo } from "react";
import type { CharacterProfile, World } from "@/contract/types";
import { CARD_MAX, compilePersona, debateCue, turnCueSentence } from "@/domain/personaPrompt";
import s from "./steps.module.css";

export const CUE_NOTE = `In group and watch, a reply's cue may add one sentence about whom the character is answering, e.g. “${turnCueSentence("second", "Hana")}”`;
export const DEBATE_NOTE = `In a debate, each argument's cue names its round, e.g. “${debateCue("rebuttal")}”`;

export interface PromptPreviewProps {
  profile: CharacterProfile;
  appearanceSummary: string;
  advisory: boolean;
  world?: Pick<World, "name" | "you">;
}

export function PromptPreview({ profile, appearanceSummary, advisory, world }: PromptPreviewProps) {
  const out = useMemo(() => compilePersona({
    profile: profile as unknown as Record<string, unknown>, appearanceSummary, advisory,
    worldName: world?.name ?? "", you: world?.you ?? null, mode: "one_on_one",
  }), [profile, appearanceSummary, advisory, world]);
  const dropped = Object.entries(out.cut.dropped).map(([k, n]) => `${n} ${k}`).join(", ");
  const note = [out.cut.capped.length ? `Shortened to fit: ${out.cut.capped.join(", ")}.` : "",
    dropped ? `The profile is over ${CARD_MAX.toLocaleString("en")} tokens, so the last items are left out: ${dropped}.` : ""]
    .filter(Boolean).join(" ");
  return (
    <div className={s.prompt}>
      <div className={s.promptHead}>
        <span>System prompt · 1:1</span>
        <span className={s.promptMeta}>≈ {out.tokens.total} tokens · read-only</span>
      </div>
      {note && <p className={s.promptNote}>{note}</p>}
      <pre className={s.promptBody}>{out.text}</pre>
      <p className={s.promptNote}>{CUE_NOTE}</p>
      <p className={s.promptNote}>{DEBATE_NOTE}</p>
    </div>
  );
}
