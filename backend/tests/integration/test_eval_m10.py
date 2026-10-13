"""M10's evaluation offline (group-watch tasks 9.2–9.9; design D23; evaluation-harness "M10 decision sets",
"Committed watch histories", "Episode recaps in the summary suite", "Free runs for group and watch", "Follow-plan and
watch timing"). Test mode, the in-process fake, no network."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from horizon.ai.decider import Choice
from horizon.evals import suites, watch_suites
from horizon.evals.runner import EVALS_DIR, Options, RunEnv
from tests.conftest import Api
from tests.sessions.kit import API

DATASETS = EVALS_DIR / "datasets"
M10_FILES = ("who_speaks/who_first.jsonl", "who_speaks/who_second.jsonl", "who_speaks/who_scene.jsonl",
             "talk_finished/talk_finished.jsonl", "emotion/emotion_watch.jsonl")


def env_for(api: Api, tmp: Path, opts: Options) -> RunEnv:
    run_dir = tmp / "evals" / "run-1" / opts.profile
    run_dir.mkdir(parents=True, exist_ok=True)
    return RunEnv(rt=api.rt, opts=opts, store=None, run_dir=run_dir, max_usd=1.0)


def load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 9.3–9.5: the sets load, compile as live and are built by the live code, deterministically ──
@pytest.mark.parametrize("rel", M10_FILES)
def test_the_m10_sets_load_and_compile_as_live(rel: str) -> None:
    rows = suites.load_dataset(DATASETS / rel)
    assert rows
    for r in rows[:10]:
        q = suites.item_question(r)
        if r["question_id"] in ("who_first", "who_scene"):
            assert isinstance(q, Choice) and "none" not in q.options       # no `none` in the first slot (G1)
        if r["question_id"] == "who_second":
            assert isinstance(q, Choice) and "none" in q.options


def test_the_builders_are_deterministic_and_use_the_live_state() -> None:
    import sys

    sys.path.insert(0, str(DATASETS / "who_speaks"))
    who = load("who_build", DATASETS / "who_speaks" / "build.py")
    prof = who.profiles()
    assert who.build_first(prof) == suites.load_dataset(DATASETS / "who_speaks" / "who_first.jsonl")
    assert who.build_second(prof) == suites.load_dataset(DATASETS / "who_speaks" / "who_second.jsonl")
    talk = load("talk_build", DATASETS / "talk_finished" / "build.py")
    assert talk.build(prof) == suites.load_dataset(DATASETS / "talk_finished" / "talk_finished.jsonl")
    slice_ = load("emotion_watch_build", DATASETS / "emotion" / "build_watch.py")
    rows = slice_.build(prof)
    assert rows == suites.load_dataset(DATASETS / "emotion" / "emotion_watch.jsonl")
    opening = next(r for r in rows if r["question_id"] == "emotion_opening")
    assert opening["item"]["state"]["mode"] == "watch" and opening["item"]["state"].get("quoted_premise")
    # the second slot's state is the follow plan's own (the user's message as quoted_message)
    second = suites.load_dataset(DATASETS / "who_speaks" / "who_second.jsonl")[0]
    assert "quoted_message" in second["item"]["state"]


def test_the_watch_part_is_built_from_the_committed_histories() -> None:
    """10.2: `who_scene` is the live cast plan's state at each labelled cut of `evals/watch/*.json`, one acceptable
    name per item (never the last speaker), all English (the user's choice), at least 20 test items (D23). G11's growth
    (10.3) adds 40 after the first 60, whose ids and splits never move."""
    import sys

    sys.path.insert(0, str(DATASETS / "who_speaks"))
    who = load("who_build", DATASETS / "who_speaks" / "build.py")
    scene = load("who_scene_build", DATASETS / "who_speaks" / "scene.py")
    rows = scene.build_scene(who.profiles())
    assert rows == suites.load_dataset(DATASETS / "who_speaks" / "who_scene.jsonl")
    assert len(rows) == 100 and sum(r["split"] == "test" for r in rows[:60]) >= 20
    assert {r["source"].split("#")[0] for r in rows[:60]} == {"watch:meridian_long", "watch:sunnyhollow"}
    for r in rows:
        label = r["label"]
        assert len(label["acceptable"]) == 1 and set(label["acceptable"]) <= set(label["candidates"])
        assert len(label["candidates"]) == 2 and r["lang"] == "en" and r["item"]["state"]["mode"] == "watch"


def test_the_ten_recap_items_come_from_the_histories() -> None:
    from horizon.evals.watch_suites import RECAP_POINTS, recap_items

    items = recap_items()
    assert len(items) == sum(len(v) for v in RECAP_POINTS.values()) == 10


async def test_decisions_reports_the_m10_parts(api: Api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A run over a few items of each M10 set on the fake: each part's report renders (the fake's numbers mean
    nothing; the code path is what's checked)."""
    await api.set_key()
    root = tmp_path / "datasets"
    for rel in M10_FILES:
        rows = suites.load_dataset(DATASETS / rel)
        keep = [r for r in rows if r["split"] == "dev"][:6] + [r for r in rows if r["split"] == "test"][:4]
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in keep), encoding="utf-8")
    monkeypatch.setattr(suites, "DATASETS", root)
    d = suites.Decisions()
    res = await d.run(env_for(api, tmp_path, Options("decisions")), d.plan(Options("decisions"), api.rt.prices, paid=True))
    text = "\n".join(res.summary)
    for part in ("who_first", "who_second", "talk_finished"):
        assert f"({part})" in text
    assert "## Emotion" in text and "margin" in text


# ── 9.2: watch-history ──
async def test_watch_history_writes_the_format_the_recaps_read(api: Api, tmp_path: Path,
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    await api.set_key()
    opts = Options("watch-history", limit=6, set="sunnyhollow")
    s = watch_suites.WatchHistory()
    env = env_for(api, tmp_path, opts)
    res = await s.run(env, s.plan(opts, api.rt.prices, paid=False))
    assert res.status == "ok"
    doc = json.loads((env.run_dir / "sunnyhollow.json").read_text(encoding="utf-8"))
    lines = [x for x in doc["lines"] if x["kind"] == "line"]
    assert len(lines) >= 6 and {"seq", "speaker", "text", "summary_upto", "summary"} <= set(lines[0])
    assert doc["premise"].startswith("The morning of the town's flower festival")
    monkeypatch.setattr(watch_suites, "WATCH_DIR", env.run_dir)
    monkeypatch.setattr(watch_suites, "RECAP_POINTS", {"sunnyhollow": (3, 6)})
    items = watch_suites.recap_items()
    assert [i["turn"] for i in items] == [3, 6]
    ctx = watch_suites.recap_context(doc, 3, watch_suites.seed_profiles())
    assert ctx.config == {"premise": doc["premise"]} and len([m for m in ctx.recent if m.author_type == "character"]) == 3


def test_watch_history_refuses_to_overwrite_a_committed_history(tmp_path: Path,
                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(watch_suites, "WATCH_DIR", tmp_path)
    monkeypatch.setattr(watch_suites, "SCRIPTS", EVALS_DIR / "watch" / "scripts")
    s = watch_suites.WatchHistory()
    assert s.refuse(Options("watch-history")) is None
    (tmp_path / "meridian_long.json").write_text("{}", encoding="utf-8")
    why = s.refuse(Options("watch-history"))
    assert why is not None and "--force" in why and "meridian_long" in why
    assert s.refuse(Options("watch-history", force=True)) is None


async def test_the_runner_stops_before_any_call_when_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from horizon.evals.runner import Runner
    from tests.conftest import make_config

    monkeypatch.setattr(watch_suites, "WATCH_DIR", tmp_path)
    (tmp_path / "sunnyhollow.json").write_text("{}", encoding="utf-8")
    said: list[str] = []
    code = await Runner(make_config(tmp_path / "data", test_mode=True), out=said.append).run(
        Options("watch-history", set="sunnyhollow", yes=True))
    assert code == 2 and "--force" in said[0] and not any(x.startswith("plan:") for x in said)


# ── 9.7: recaps ──
async def test_recaps_run_on_canned_answers_and_print_failures(api: Api, tmp_path: Path,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    from horizon.evals.content import Summary
    from horizon.gateway.fake import load_canned

    await api.set_key()
    hist = {"schemaVersion": 1, "id": "sunnyhollow", "mode": "watch", "world": "wld_seedSunnyHollow",
            "cast": ["chr_seedHana", "chr_seedRin", "chr_seedTakeshi"], "premise": "A quiet morning.", "language": "en",
            "lines": [{"seq": i + 2, "kind": "line", "speaker": ["chr_seedHana", "chr_seedRin", "chr_seedTakeshi"][i % 3],
                       "text": f"Line {i}.", "summary_upto": None, "summary": None} for i in range(12)]}
    (tmp_path / "sunnyhollow.json").write_text(json.dumps(hist), encoding="utf-8")
    monkeypatch.setattr(watch_suites, "WATCH_DIR", tmp_path)
    monkeypatch.setattr(watch_suites, "RECAP_POINTS", {"sunnyhollow": (4, 8, 12)})
    assert api.rt.fake is not None
    purpose, canned = load_canned("episode-recaps")
    api.rt.fake.set_canned(purpose, canned)
    s = Summary()
    opts = Options("summary", set="recaps")
    res = await s.run(env_for(api, tmp_path, opts), s.plan(opts, api.rt.prices, paid=True))
    rows = [r for r in res.rows if r["id"].startswith("recap-")]
    assert len(rows) == 3 and all(r["within_words"] for r in rows)       # the third canned recap was cut to ≤ 120
    assert any(x.startswith("## Episode recaps (3)") for x in res.summary)
    over = {**rows[0], "words": 135, "within_words": False, "recap": "x " * 135}
    lines = watch_suites.recap_report([over, *rows[1:]])
    assert lines[0].startswith("## Episode recaps (3): ") and any("READ" in x and "135 words" in x for x in lines)
    assert any("lines:" in x for x in lines)


# ── 9.8: freerun ──
async def _agent(api: Api) -> None:
    await api.set_key()
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": "agent"})).status_code == 204


@pytest.mark.parametrize("mode", ["group", "watch"])
async def test_freerun_reports_its_signals(api: Api, tmp_path: Path, mode: str) -> None:
    await _agent(api)
    opts = Options("freerun", profile="agent", mode=mode, limit=3)
    s = watch_suites.FreeRun()
    res = await s.run(env_for(api, tmp_path, opts), s.plan(opts, api.rt.prices, paid=False))
    text = "\n".join(res.summary)
    assert "busiest speaker" in text and "no target" in text
    assert ("timeouts" in text) if mode == "group" else ("the guard fired" in text and "the steer fired" in text)


def test_freerun_counts_timeouts_apart_from_none() -> None:
    def reply(i: int, answer: str | None, second: bool = False) -> dict[str, Any]:
        rows = [] if answer is None else [{"id": "who_second", "answer": answer,
                                          "result": "fallback" if "late" in answer else "used"}]
        routing = {"question": "who speaks up now?"} if second else {}
        return {"author": {"type": "character", "characterId": f"chr_{i % 3}"}, "content": "x",
                "trace": {"routing": routing, "system1": {"questions": rows}}}

    msgs = [reply(0, "none"), reply(1, "none"), reply(2, "none"), reply(3, "no second reply (late)"),
            reply(4, "no second reply (late)"), *[reply(i, None) for i in range(5, 12)], reply(12, None, second=True)]
    text = "\n".join(watch_suites.freerun_report("group", msgs, 12))
    assert "3 none, 2 timeouts (late)" in text and "second replies: 1/12" in text


# ── 9.9: the timing parts ──
def test_slow_spells_are_grouped_and_reported_apart() -> None:
    lat = [300.0, 2500.0, 2600.0, 2100.0, 2700.0, 350.0, 2500.0, 2600.0, 380.0]
    assert watch_suites.spells(lat) == [(1, 4)]                           # 4 in a row; the later pair is no spell
    rows = [{"s_ms": 1.0, "l_ms": x} for x in lat]
    m = watch_suites.follow_misses(rows, f_ms=12.3, deadline_ms=400.0)
    assert m["missed"] == 6 and m["spells"] == [(1, 4)]
    assert abs(m["rate"] - 6 / 9) < 1e-9 and abs(m["rate_without_spells"] - 2 / 5) < 1e-9
    text = "\n".join(watch_suites.follow_report(rows))
    assert "requests 2–5" in text and "without them 40%" in text and "FAIL" in text


def test_the_miss_rule_is_s_plus_l_past_f_plus_400() -> None:
    rows = [{"s_ms": 5.0, "l_ms": 400.0}, {"s_ms": 5.0, "l_ms": 410.0}]   # 405 ≤ 412.3; 415 > 412.3
    assert watch_suites.follow_misses(rows, f_ms=12.3)["missed"] == 1


async def test_latency_follow_part_on_the_fake(api: Api, tmp_path: Path) -> None:
    from horizon.evals.latency import Latency

    await _agent(api)
    opts = Options("latency", profile="agent", part="follow", limit=3)
    s = Latency()
    res = await s.run(env_for(api, tmp_path, opts), s.plan(opts, api.rt.prices, paid=False))
    assert len(res.rows) == 3 and all(r["s_ms"] >= 0 and r["l_ms"] >= 0 and r["tokens"] > 0 for r in res.rows)
    assert res.summary[0].startswith("## Follow-plan timing (D9): ")
    assert api.rt.fake is not None and api.rt.fake.counts["decisions"] >= 3


async def test_latency_watch_part_on_the_fake(api: Api, tmp_path: Path) -> None:
    from horizon.evals.latency import Latency

    await _agent(api)
    opts = Options("latency", profile="agent", part="watch", limit=4)
    s = Latency()
    res = await s.run(env_for(api, tmp_path, opts), s.plan(opts, api.rt.prices, paid=False))
    text = "\n".join(res.summary)
    assert "## Watch timing (Fast pace): " in text and "the plan made ahead: used" in text
    assert "turn.end → next first token: p50" in text


def test_shutil_is_available() -> None:   # the history copy in the smoke path uses it
    assert shutil.copyfile is not None
