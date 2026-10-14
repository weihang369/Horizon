// O26 End debate early (MULTI-07 AC4) — Builder D. Before closing: "Go to verdict now (≈ $x)" or
// "End without verdict". Destructive-ish but recoverable, so the safe default focus is Cancel.
import { useState } from "react";
import { client } from "../../client";
import { useRushHour } from "../../client/hooks";
import { chatCostUsd, decisionCostUsd } from "../../domain/cost";
import { PRICING } from "../../mock/pricing.config";
import type { PricingTable } from "../../domain/cost";
import type { PricePeriod } from "../../domain/rushHour";
import type { DebateConfig } from "../../contract/types";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { reportError } from "../../app/errors";
import { toast } from "../../app/layers";
import { navigate } from "../../router";
import { Button, Modal, formatUsd } from "../../ui";
import { useSlot } from "./shared";
import s from "./Overlays.module.css";

/** M11 (debate D16): one estimate for the dearer of the real verdicts, `agent`'s: Jev's rubric scores (≈ 6,000 tokens on
 *  the decision price, no peak multiplier) plus DeepSeek's prose (≈ 6,000 in and 300 out on the chat price, which the
 *  peak multiplier raises). `naive`'s single call is about $0.0011, so "≈" holds for both. */
export const VERDICT_JEV_TOKENS = 6000;
export const VERDICT_PROSE = { tokensIn: 6000, tokensOut: 300 };

export function verdictEstimateUsd(period: PricePeriod, pricing: PricingTable = PRICING): number {
  return decisionCostUsd(VERDICT_JEV_TOKENS, pricing.decision) + chatCostUsd(VERDICT_PROSE, pricing.chat, period);
}

export function EndDebate({ sessionId, close }: OverlayComponentProps<"O26">) {
  const slot = useSlot(sessionId);
  const session = slot?.runtime?.session;
  const cfg = session?.config as DebateConfig | null;
  const phase = slot?.runtime?.phase?.phase;
  const [busy, setBusy] = useState<"verdict" | "end" | null>(null);
  const verdictOff = cfg?.verdictBy === "none";
  const estimate = verdictEstimateUsd(useRushHour().period);

  const go = async (withVerdict: boolean) => {
    setBusy(withVerdict ? "verdict" : "end");
    try {
      await client.debate.endDebate(sessionId, withVerdict);
      close();
      if (withVerdict && session) navigate({ name: "verdict", worldId: session.worldId, sessionId });
      else toast({ variant: "info", text: "Debate ended without a verdict." });
    } catch (err) {
      reportError(err);
      setBusy(null);
    }
  };

  return (
    <Modal
      title="End the debate early?"
      tape="End debate"
      size="sm"
      onClose={close}
      actions={
        <>
          <Button variant="ghost" onClick={close} autoFocus>Keep debating</Button>
          <Button variant="secondary" disabled={!!busy} onClick={() => void go(false)}>
            {busy === "end" ? "Ending…" : "End without verdict"}
          </Button>
          {!verdictOff && (
            <Button disabled={!!busy} onClick={() => void go(true)}>
              {busy === "verdict" ? "Calling the arbiter…" : `Go to verdict now (≈ ${formatUsd(estimate)})`}
            </Button>
          )}
        </>
      }
    >
      <p className={s.modalText}>
        {phase && phase !== "setup" ? `You're in the ${phase} round.` : "The debate hasn't reached its closing statements."}{" "}
        {verdictOff
          ? "This debate is set to summary only, so ending now just closes it."
          : cfg?.verdictBy === "user"
            ? "Going to the verdict now asks you to pick the stronger case."
            : "The arbiter can still judge what's been said so far, or you can stop here with no verdict."}
      </p>
    </Modal>
  );
}
