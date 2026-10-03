// HTTP transport for the HttpClient (doc backend/03 §1–§2, §5). Owner: SWE.
// - Every non-2xx response becomes a HorizonError built from the `{ error }` envelope (details kept).
// - A request that can't reach the server rejects with `network` (retryable).
// - Every POST carries an Idempotency-Key; the one automatic retry (network failure only) reuses it, so a create
//   whose response was lost is never applied twice.
import { HorizonError } from "../../contract/errors";
import type { HorizonErrorShape } from "../../contract/errors";
import type { ErrorCode } from "../../contract/types";

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;
export type Query = Record<string, string | number | boolean | undefined>;

export interface TransportOptions {
  /** e.g. "/api/v1" (browser, via the Vite proxy) or "http://127.0.0.1:8000/api/v1" (tests). */
  baseUrl: string;
  fetch?: FetchLike;
  /** Key generator (tests pin it). */
  newKey?: () => string;
}

const STATUS_CODE: Record<number, ErrorCode> = { 400: "validation", 404: "not_found", 409: "conflict", 413: "validation", 422: "validation", 429: "rate_limited", 504: "timeout" };

function randomKey(): string {
  const c = globalThis.crypto;
  if (c?.randomUUID) return c.randomUUID();
  return `k-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

export class Transport {
  readonly baseUrl: string;
  private readonly fetchImpl: FetchLike;
  private readonly newKey: () => string;

  constructor(opts: TransportOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/+$/, "");
    this.fetchImpl = opts.fetch ?? ((input, init) => globalThis.fetch(input, init));
    this.newKey = opts.newKey ?? randomKey;
  }

  url(path: string, query?: Query): string {
    const q = query
      ? Object.entries(query).filter(([, v]) => v !== undefined).map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join("&")
      : "";
    return `${this.baseUrl}${path}${q ? `?${q}` : ""}`;
  }

  get<T>(path: string, query?: Query): Promise<T> {
    return this.send<T>("GET", path, { query });
  }

  post<T>(path: string, body?: unknown): Promise<T> {
    return this.send<T>("POST", path, { body, idempotent: true });
  }

  patch<T>(path: string, body: unknown): Promise<T> {
    return this.send<T>("PATCH", path, { body });
  }

  delete(path: string): Promise<void> {
    return this.send<void>("DELETE", path, {});
  }

  private async send<T>(method: string, path: string, o: { body?: unknown; query?: Query; idempotent?: boolean }): Promise<T> {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (o.body !== undefined) headers["Content-Type"] = "application/json";
    if (o.idempotent) headers["Idempotency-Key"] = this.newKey();
    const init: RequestInit = { method, headers, body: o.body === undefined ? undefined : JSON.stringify(o.body) };
    const url = this.url(path, o.query);
    let res: Response;
    try {
      res = await this.fetchImpl(url, init);
    } catch (first) {
      if (!o.idempotent) throw networkError(first);
      try {
        res = await this.fetchImpl(url, init); // same Idempotency-Key: the server replays if the first one landed
      } catch (second) {
        throw networkError(second);
      }
    }
    if (!res.ok) throw await toError(res);
    if (res.status === 204) return undefined as T;
    const text = await res.text();
    return (text ? JSON.parse(text) : null) as T;
  }
}

function networkError(e: unknown): HorizonError {
  return new HorizonError("network", e instanceof Error && e.message ? `Can't reach the Horizon server (${e.message}).` : undefined, { retryable: true });
}

async function toError(res: Response): Promise<HorizonError> {
  let shape: Partial<HorizonErrorShape> | undefined;
  try {
    const body = (await res.json()) as { error?: Partial<HorizonErrorShape> };
    shape = body?.error;
  } catch {
    shape = undefined;
  }
  const code = (shape?.code ?? STATUS_CODE[res.status] ?? "provider_error") as ErrorCode;
  return new HorizonError(code, shape?.message, {
    retryable: shape?.retryable,
    retryAfterSec: shape?.retryAfterSec ?? (Number(res.headers.get("Retry-After")) || undefined),
    details: shape?.details,
  });
}
