// Central error routing (STATE-03/04/06).
// Builders call reportError(e) in catch blocks: missing/invalid key → O05, budget → O21, everything else → a toast
// (inline ErrorTapes are the feature's job). Typed input is never cleared here.
import type { HorizonErrorShape } from "../contract/errors";
import { ERROR_COPY, toHorizonError } from "../contract/errors";
import { entities } from "../stores/entities";
import { ui } from "../stores/ui";
import { openOverlay, toast } from "./layers";

export function reportError(err: unknown, opts?: { context?: string; retry?: () => void; quiet?: boolean }): HorizonErrorShape {
  const e = toHorizonError(err).toJSON();
  switch (e.code) {
    case "missing_key":
    case "invalid_key":
      openOverlay("O05", { reason: e.code === "invalid_key" ? ERROR_COPY.invalid_key : opts?.context });
      break;
    case "daily_budget_exceeded":
    case "creation_budget_exceeded": {
      const st = entities.getState().settings;
      const daily = e.code === "daily_budget_exceeded";
      // Audit 03-F12: the global `budget.reached` event carries the real figures and may have opened O21 already; the
      // refusal itself has none for a creation cap, so it never replaces that dialog with $0.
      if (!daily && ui.getState().layers.some((l) => l.id === "O21")) break;
      const num = (v: unknown) => (typeof v === "number" ? v : undefined);
      openOverlay("O21", {
        scope: daily ? "daily" : "creation",
        spentUsd: num(e.details?.spentUsd) ?? (daily ? st?.spentTodayUsd ?? 0 : 0),
        capUsd: num(e.details?.capUsd) ?? (daily ? st?.budget.dailyCapUsd ?? 0 : st?.budget.perCharacterCreationCapUsd ?? 0),
      });
      break;
    }
    default:
      if (!opts?.quiet) {
        toast({
          variant: "error",
          text: e.code === "rate_limited" && e.retryAfterSec ? `Too many requests. Try again in ${e.retryAfterSec} s.` : e.message,
          ...(opts?.retry && e.retryable ? { action: { label: "Retry", run: opts.retry } } : {}),
        });
      }
  }
  return e;
}

/** Wrap a command: `run(() => client.chat.send(…))` resolves to undefined on failure after routing the error. */
export async function run<T>(fn: () => Promise<T>, opts?: Parameters<typeof reportError>[1]): Promise<T | undefined> {
  try {
    return await fn();
  } catch (err) {
    reportError(err, opts);
    return undefined;
  }
}
