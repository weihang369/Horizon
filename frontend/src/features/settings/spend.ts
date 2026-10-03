// Spend view helpers (SET-09). Owner: Builder A.
export interface SpendRow { id: string; usd: number }

/** Top-N rows by spend, largest first; zero rows dropped. */
export function spendRows(by: Record<string, number>, n: number): SpendRow[] {
  return Object.entries(by)
    .filter(([, usd]) => usd > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, n)
    .map(([id, usd]) => ({ id, usd }));
}
