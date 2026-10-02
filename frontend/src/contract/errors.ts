// HorizonError: the one error type every HorizonClient call rejects with (doc 05 ErrorCode).
import type { ErrorCode } from "./types";

export interface HorizonErrorShape {
  code: ErrorCode;
  message: string;
  retryable: boolean;
  /** Seconds until a retry makes sense (rate_limited). */
  retryAfterSec?: number;
}

export class HorizonError extends Error implements HorizonErrorShape {
  readonly code: ErrorCode;
  readonly retryable: boolean;
  readonly retryAfterSec?: number;

  constructor(code: ErrorCode, message?: string, opts?: { retryable?: boolean; retryAfterSec?: number }) {
    super(message ?? ERROR_COPY[code]);
    this.name = "HorizonError";
    this.code = code;
    this.retryable = opts?.retryable ?? DEFAULT_RETRYABLE[code];
    this.retryAfterSec = opts?.retryAfterSec;
  }

  toJSON(): HorizonErrorShape {
    return { code: this.code, message: this.message, retryable: this.retryable, retryAfterSec: this.retryAfterSec };
  }
}

export function isHorizonError(e: unknown): e is HorizonError {
  return e instanceof HorizonError;
}

/** Normalises anything thrown into a HorizonError (unknown errors become `network`). */
export function toHorizonError(e: unknown): HorizonError {
  if (e instanceof HorizonError) return e;
  return new HorizonError("network", e instanceof Error ? e.message : String(e));
}

/** STATE-03 copy (doc 02). UI may override per context. */
export const ERROR_COPY: Record<ErrorCode, string> = {
  missing_key: "Horizon needs your OpenRouter key to think.",
  invalid_key: "That key was rejected by OpenRouter.",
  insufficient_credits: "Your OpenRouter balance ran out.",
  rate_limited: "Too many requests. Retrying in 12 s…",
  content_refused: "The model declined this request. Try different wording.",
  provider_error: "The provider failed to generate this.",
  daily_budget_exceeded: "Today's budget is reached.",
  creation_budget_exceeded: "This character's creation budget is reached.",
  energy_exhausted: "This character is asleep (⚡ 0).",
  timeout: "That took too long.",
  network: "Can't reach the Horizon server.",
};

export const DEFAULT_RETRYABLE: Record<ErrorCode, boolean> = {
  missing_key: false,
  invalid_key: false,
  insufficient_credits: true,
  rate_limited: true,
  content_refused: true,
  provider_error: true,
  daily_budget_exceeded: false,
  creation_budget_exceeded: false,
  energy_exhausted: false,
  timeout: true,
  network: true,
};
