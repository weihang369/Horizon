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
    assert r.reply_max_tokens.for_mode("one_on_one") == 200 and r.reply_max_tokens.for_mode("one_on_one", deep=True) == 300
    assert r.reply_max_tokens.for_mode("group") == 150 and r.reply_max_tokens.for_mode("watch") == 150
    assert [r.reply_max_tokens.for_mode("debate", x) for x in ("short", "medium", "long")] == [200, 320, 480]
    assert (r.coalesce_max_chars, r.coalesce_max_ms) == (48, 50)
    # docs/ai/05 X2 (persona-context 4.1): windows per mode
    assert r.window_tokens.as_dict() == {"one_on_one": 6000, "group": 9000, "watch": 9000, "debate": 9000}
    assert r.llm("summary").max_tokens == 600
    assert (r.idle_release_ms, r.prefetch_max, r.llm_concurrency) == (600_000, 2, 4)
    assert r.switch("persona.repeatHint") is False and r.switch("context.voiceReminder") is False   # M8: both off


def test_an_old_single_window_still_loads() -> None:
    from horizon.domain.runtime_config import WindowSizes

    assert WindowSizes.from_json(7000).as_dict() == {"one_on_one": 7000, "group": 7000, "watch": 7000, "debate": 7000}


def test_the_emotion_fade_set_loads() -> None:   # M9 (turn-plan-emotion task 2.6; docs/ai/06 E3, doc 13 W12)
    assert load_runtime_config(SEED).runtime.emotion_fade == frozenset({"surprised", "embarrassed"})


def test_the_host_waits_load() -> None:   # M11 (debate task 6.1; doc 08 V6; design D11)
    r = load_runtime_config(SEED).runtime
    assert (r.host_welcome_wait_ms, r.host_banner_wait_ms) == (3000.0, 1500.0)
