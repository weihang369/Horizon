// The masked key hint shown after saving (SET-01 AC2: only `sk-or-…a1b2`). The key itself is never stored here:
// only its last 4 characters, so Settings can show which key is active. Owner: Builder A.
const KEY = "horizon.keyHint.v1";

export function maskKey(last4: string | null): string {
  return last4 ? `sk-or-…${last4}` : "sk-or-…";
}

export function saveKeyHint(key: string | null): void {
  try {
    if (!key) localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, key.trim().slice(-4));
  } catch { /* private mode */ }
}

export function readKeyHint(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}
