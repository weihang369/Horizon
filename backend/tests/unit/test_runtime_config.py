"""`seed/runtime.json` loads every field (session-runtime design D9)."""

from __future__ import annotations

import json
from pathlib import Path

from horizon.domain.runtime_config import load_runtime_config

SEED = Path(__file__).resolve().parents[3] / "seed"


def test_every_field_loads() -> None:
    cfg = load_runtime_config(SEED)
    raw = json.loads((SEED / "runtime.json").read_text(encoding="utf-8"))["data"]
    t, r = cfg.timing, cfg.runtime
    assert t.first_token_ms == raw["timing"]["firstTokenMs"] == 1500
    assert (t.thinking_ms, t.tokens_per_sec, t.chars_per_token, t.tokens_per_event, t.turn_gap_ms) == (60, 40, 4, 3, 400)
    assert t.reaction_delay_ms == (300, 800) and t.reaction_chance == 0.7
    assert t.emotion_timing == {"before": 0.7, "early": 0.25, "late": 0.05} and t.late_emotion_ms == 1200
    assert (t.debate_start_ms, t.watch_start_ms, t.greeting_ms) == (1600, 800, 300)
    assert r.reply_max_tokens.for_mode("one_on_one") == 350
    assert r.reply_max_tokens.for_mode("group") == 250 and r.reply_max_tokens.for_mode("watch") == 220
    assert [r.reply_max_tokens.for_mode("debate", x) for x in ("short", "medium", "long")] == [200, 320, 480]
    assert (r.window_tokens, r.coalesce_max_chars, r.coalesce_max_ms) == (6000, 48, 50)
    assert (r.idle_release_ms, r.prefetch_max, r.llm_concurrency) == (600_000, 2, 4)
