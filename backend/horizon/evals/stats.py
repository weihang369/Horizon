"""`horizon stats` and `horizon eval capture` (docs/ai/02 B10, B12; ai-foundation design D36; task 7.8).

Both open the user's database **read-only** (SQLite `mode=ro`), make no network call and print plain text.

`stats [--days N]` reports, from live (non-seed) rows only:
- face and first-word latency p50/p90 per mode (`session_events`: `turn.start` → the first `emotion` / `token`);
- cost per reply turn by purpose, the chat cache-hit %, Jev's share of spend and its latency (the ledger);
- the late rate per decision purpose (`finish_reason`, design D6);
- per-question fallback rates from the traces' `system1` rows.

`eval capture <messageId>` writes that message's `ai_calls` rows (call and turn) to `data/evals/cases/<id>.json`; with
no rows it exits non-zero ("capture was off for this message").
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from horizon.evals.metrics import percentile


@contextmanager
def read_only(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _ms(a: str, b: str) -> float:
    return (dt.datetime.fromisoformat(b.replace("Z", "+00:00"))
            - dt.datetime.fromisoformat(a.replace("Z", "+00:00"))).total_seconds() * 1000


def _since(days: int | None) -> str:
    if not days:
        return "0000"
    return (dt.datetime.now(dt.UTC) - dt.timedelta(days=days)).isoformat().replace("+00:00", "Z")


def _p(xs: list[float]) -> str:
    return f"p50 {percentile(xs, 0.5):.0f} ms · p90 {percentile(xs, 0.9):.0f} ms (n={len(xs)})" if xs else "no data"


def stats(db_path: Path, days: int | None = None) -> str:
    if not db_path.is_file():
        return "horizon stats: no database yet (run the app first); no live data"
    since = _since(days)
    lines: list[str] = [f"horizon stats{f' (last {days} days)' if days else ''}"]
    with read_only(db_path) as c:
        live = c.execute("SELECT COUNT(*) FROM usage_records WHERE is_seed = 0 AND at >= ?", (since,)).fetchone()[0]
        if not live:
            return lines[0] + "\nno live data yet (seed rows and replays are skipped)"
        # latency per mode from the event log (live sessions only; seed sessions are replays)
        face: dict[str, list[float]] = defaultdict(list)
        first: dict[str, list[float]] = defaultdict(list)
        rows = c.execute(
            "SELECT s.mode, e.message_id, e.type, e.at FROM session_events e JOIN sessions s ON s.id = e.session_id "
            "WHERE s.is_seed = 0 AND e.at >= ? AND e.type IN ('turn.start','emotion','token') ORDER BY e.seq",
            (since,)).fetchall()
        start: dict[str, tuple[str, str]] = {}
        seen_face: set[str] = set()
        seen_tok: set[str] = set()
        for r in rows:
            mid = r["message_id"]
            if not mid:
                continue
            if r["type"] == "turn.start":
                start.setdefault(mid, (r["mode"], r["at"]))
            elif mid in start and r["type"] == "emotion" and mid not in seen_face:
                seen_face.add(mid)
                face[start[mid][0]].append(_ms(start[mid][1], r["at"]))
            elif mid in start and r["type"] == "token" and mid not in seen_tok:
                seen_tok.add(mid)
                first[start[mid][0]].append(_ms(start[mid][1], r["at"]))
        lines.append("\nLatency (turn.start →):")
        for mode in sorted(set(face) | set(first)):
            lines.append(f"  {mode:<11} face {_p(face[mode])}; first word {_p(first[mode])}")
        # cost by purpose
        replies = c.execute("SELECT COUNT(DISTINCT message_id) FROM usage_records WHERE is_seed = 0 AND at >= ? "
                            "AND purpose = 'reply' AND message_id IS NOT NULL", (since,)).fetchone()[0] or 0
        lines.append(f"\nCost per reply turn by purpose ({replies} reply turn(s)):")
        total = 0.0
        jev = 0.0
        for r in c.execute("SELECT purpose, category, SUM(cost_usd) AS usd, COUNT(*) AS n FROM usage_records "
                           "WHERE is_seed = 0 AND at >= ? GROUP BY purpose, category ORDER BY usd DESC", (since,)):
            total += float(r["usd"] or 0)
            jev += float(r["usd"] or 0) if r["category"] == "decision" else 0.0
            per = float(r["usd"] or 0) / replies if replies else 0.0
            lines.append(f"  {r['purpose']:<16} ${per:.6f} per turn · {r['n']} call(s)")
        hit = c.execute("SELECT SUM(tokens_cached), SUM(tokens_in) FROM usage_records WHERE is_seed = 0 AND at >= ? "
                        "AND category = 'chat'", (since,)).fetchone()
        pct = 100 * float(hit[0] or 0) / float(hit[1]) if hit[1] else 0.0
        lat = [float(r[0]) for r in c.execute("SELECT latency_ms FROM usage_records WHERE is_seed = 0 AND at >= ? "
                                              "AND category = 'decision' AND latency_ms IS NOT NULL", (since,))]
        lines += [f"\nChat cache hits: {pct:.0f}% of input tokens",
                  f"Jev: {100 * jev / total if total else 0:.0f}% of spend; latency {_p(lat)}"]
        # late rate per decision purpose
        lines.append("\nLate decisions (answered after their deadline):")
        for r in c.execute("SELECT purpose, SUM(finish_reason = 'late') AS late, COUNT(*) AS n FROM usage_records "
                           "WHERE is_seed = 0 AND at >= ? AND category = 'decision' GROUP BY purpose", (since,)):
            lines.append(f"  {r['purpose']:<16} {r['late'] or 0}/{r['n']}")
        # fallbacks per question from system1 rows
        fb: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for (trace,) in c.execute("SELECT t.trace FROM turn_traces t JOIN messages m ON m.id = t.message_id "
                                  "JOIN sessions s ON s.id = m.session_id WHERE s.is_seed = 0 AND t.created_at >= ?",
                                  (since,)):
            doc = json.loads(trace) if isinstance(trace, str) else trace
            for q in ((doc or {}).get("system1") or {}).get("questions") or []:
                k = f"{q.get('purpose')}/{q.get('id')}"
                fb[k][1] += 1
                fb[k][0] += q.get("result") == "fallback"
        lines.append("\nFallbacks per question (System 1 rows):")
        lines += [f"  {k:<24} {v[0]}/{v[1]}" for k, v in sorted(fb.items())] or ["  none recorded"]
    return "\n".join(lines)


def capture_case(db_path: Path, message_id: str, out_dir: Path) -> Path | None:
    if not db_path.is_file():
        return None
    with read_only(db_path) as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM ai_calls WHERE message_id = ? ORDER BY created_at, id",
                                            (message_id,))]
        for r in rows:
            for k in ("request", "response"):
                if isinstance(r.get(k), str):
                    r[k] = json.loads(r[k])
        have = {r["id"] for r in rows}
        linked = [i for r in rows if r["kind"] == "turn" for i in (r.get("response") or {}).get("callIds") or []
                  if i not in have]
        if linked:   # turn-level calls (the route decision) flushed before their turn linked them
            extra = [dict(r) for r in c.execute(f"SELECT * FROM ai_calls WHERE id IN ({','.join('?' * len(linked))})",
                                                linked)]
            for r in extra:
                for k in ("request", "response"):
                    if isinstance(r.get(k), str):
                        r[k] = json.loads(r[k])
            rows = sorted([*rows, *extra], key=lambda r: (r["created_at"], r["id"]))
    if not rows:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{message_id}.json"
    doc: dict[str, Any] = {"messageId": message_id, "rows": rows}
    p.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return p
