"""AppSettings on read (doc 02 §3.1, http-api spec): the seed file, overlaid by `data/settings.local.json`, plus the
fields that are computed per request.

Computed: `spentTodayUsd` (today's ledger in HORIZON_TZ), `pricing` (the Clock), `energy.estReplyPoints` and
`models.embedding` (config-owned; a local override can't move them), and `openRouterKeyStatus`/`demoMode` from the
key store (M2, openrouter-key spec). The key itself is never part of AppSettings.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.db import tables as t
from horizon.domain.clock import Clock
from horizon.domain.timeutil import to_iso

log = logging.getLogger("horizon.settings")


def deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def read_seed_settings(seed_dir: Path) -> dict[str, Any]:
    doc = json.loads((seed_dir / "settings.json").read_text(encoding="utf-8"))
    data: dict[str, Any] = doc["data"]
    return data


def read_local_settings(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("ignoring unreadable %s", path.name)
        return {}
    return data if isinstance(data, dict) else {}


def local_day(clock: Clock, at_iso: str) -> str:
    from horizon.domain.timeutil import parse_iso

    return clock.calendar.today(parse_iso(at_iso)).isoformat()


async def spent_today(conn: AsyncConnection, clock: Clock) -> float:
    today = clock.calendar.today(clock.now()).isoformat()
    total = (await conn.execute(select(func.coalesce(func.sum(t.usage_records.c.cost_usd), 0.0))
                                .where(t.usage_records.c.local_day == today))).scalar_one()
    return round(float(total) + clock.spend_bias_usd, 6)   # the bias is 0 outside the `daily_cap` test scenario


async def app_settings(conn: AsyncConnection, *, seed: dict[str, Any], local: dict[str, Any], clock: Clock,
                       key_status: str = "missing") -> dict[str, Any]:
    s = deep_merge(seed, local)
    s["models"] = {**s["models"], "embedding": seed["models"]["embedding"]}
    s["energy"] = {**s["energy"], "estReplyPoints": dict(seed["energy"]["estReplyPoints"])}
    s["openRouterKeyStatus"] = key_status
    s["demoMode"] = key_status != "set"
    s["spentTodayUsd"] = await spent_today(conn, clock)
    s["pricing"] = {"period": clock.pricing_period(), "nextChangeAt": to_iso(clock.next_change_at())}
    return s


# ── PATCH /settings (http-api "Settings update", design D12) ─────────────────────
# Computed or config-owned: ignored when a patch carries them (the portable contract test expects "ignored", OQ-E).
IGNORED_TOP = ("openRouterKeyStatus", "demoMode", "spentTodayUsd", "pricing", "models")
IGNORED_ENERGY = ("estReplyPoints",)


def strip_read_only(patch: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in patch.items() if k not in IGNORED_TOP}
    energy = out.get("energy")
    if isinstance(energy, dict):
        out["energy"] = {k: v for k, v in energy.items() if k not in IGNORED_ENERGY}
    return out


def range_problems(s: dict[str, Any]) -> list[str]:
    """Business rules the schema can't express. Returns the offending field paths."""
    bad: list[str] = []

    def positive(path: str, v: Any) -> None:
        if not isinstance(v, int | float) or isinstance(v, bool) or v <= 0:
            bad.append(path)

    b, e = s.get("budget", {}), s.get("energy", {})
    positive("budget.dailyCapUsd", b.get("dailyCapUsd"))
    positive("budget.perCharacterCreationCapUsd", b.get("perCharacterCreationCapUsd"))
    pct = b.get("warnAtPct")
    if not isinstance(pct, int | float) or isinstance(pct, bool) or not 0 < pct <= 100:
        bad.append("budget.warnAtPct")
    for k in ("defaultMaxPoints", "usdPerPoint", "topUpStepPoints"):
        positive(f"energy.{k}", e.get(k))
    for role, model in (s.get("modelOverrides") or {}).items():
        if not isinstance(model, str) or not model.strip() or "latest" in model:
            bad.append(f"modelOverrides.{role}")
    return bad
