// Cursor paging (doc backend/03 §1): paginated routes return `{ items, nextCursor }`; the HorizonClient methods keep
// returning plain arrays, so the HttpClient follows `nextCursor` until it is null. Owner: SWE.
import type { Query, Transport } from "./transport";

export interface Page<T> { items: T[]; nextCursor: string | null }

export const PAGE_LIMIT = 1000;

export async function collect<T>(t: Transport, path: string, query: Query = {}): Promise<T[]> {
  const out: T[] = [];
  let cursor: string | null | undefined;
  do {
    const page = await t.get<Page<T>>(path, { ...query, limit: PAGE_LIMIT, ...(cursor ? { cursor } : {}) });
    out.push(...page.items);
    cursor = page.nextCursor;
  } while (cursor);
  return out;
}
