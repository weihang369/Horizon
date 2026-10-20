"""`horizon eval conversations` on the in-process fake (images-music design D11; evaluation-harness "The conversations
suite"; task 6.1). Test mode, no network, $0."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from horizon.evals import conversations as cv
from horizon.evals import frozen
from horizon.evals.runner import Options
from tests.integration.test_eval_runner import runner


def run_dir(tmp: Path) -> Path:
    (run,) = [p for p in (tmp / "evals").iterdir() if p.is_dir() and "conversations" in p.name]
    return run


def lines(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.is_file() else []


async def test_smoke_one_unit_per_mode_both_profiles_at_0(tmp_path: Path) -> None:
    r, _ = runner(tmp_path)
    assert await r.run(Options("conversations", limit=1, yes=True)) == 0
    run = run_dir(tmp_path)
    rows = lines(run / "naive" / "replies.jsonl")
    assert sorted(x["mode"] for x in rows) == ["debate", "group", "one_on_one", "watch"]
    assert all("text" in x["replies"][p] for x in rows for p in cv.PROFILES)
    assert all(x["judged"].get("p_agent_better") is not None for x in rows)
    assert all(x["replies"]["naive"].get("raw") for x in rows)               # the gateway hook is wired (M15 8.9)
    states = lines(run / "naive" / "judge_states.jsonl")
    assert {s["question_id"] for s in states} >= {cv.VOICE, cv.FACT, cv.IN_STORY, cv.PAIRWISE}
    report = (run / "naive" / "report.md").read_text(encoding="utf-8")
    assert "## Conversations: 4 of 4 unit(s)" in report and "NOT COUNTED" in report
    assert (run / "agent").is_dir()                                           # the other profile's own copy


def history_rows(db: Path, title: str, upto: int) -> tuple[list[tuple], list[tuple]]:
    with sqlite3.connect(db) as c:
        sid = c.execute("SELECT id FROM sessions WHERE title = ?", (title,)).fetchone()[0]
        msgs = c.execute("SELECT seq, author_type, author_character_id, kind, content FROM messages WHERE session_id = ? "
                         "AND seq <= ? ORDER BY seq", (sid, upto)).fetchall()
        sums = c.execute("SELECT upto_seq, kind, text FROM session_summaries WHERE session_id = ?", (sid,)).fetchall()
    return msgs, sums


async def test_both_profiles_reply_from_the_same_stored_history(tmp_path: Path) -> None:
    t = frozen.load("long_one_on_one_en")
    unit = t["compared"][0]
    r, _ = runner(tmp_path)
    assert await r.run(Options("conversations", set=t["id"], limit=1, yes=True)) == 0
    run = run_dir(tmp_path)
    rb = cv.rebuild(t, unit)
    assert rb.summary is not None                                             # past the drop: the summary in force
    got = {p: history_rows(run / p / "horizon.db", f"conversations {t['id']}", len(rb.lines)) for p in cv.PROFILES}
    assert got["agent"] == got["naive"]
    msgs, sums = got["agent"]
    assert len(msgs) == len(rb.lines) and [m[4] for m in msgs] == [ln["content"] for ln in rb.lines]
    assert sums == [(rb.summary[0], "rolling", rb.summary[1])]
    with sqlite3.connect(run / "agent" / "horizon.db") as a, sqlite3.connect(run / "naive" / "horizon.db") as n:
        q = "SELECT id, text FROM memory_items WHERE character_id = 'chr_seedAmara' ORDER BY id"
        assert a.execute(q).fetchall() == n.execute(q).fetchall() != []      # the same start-of-session memory list


def test_the_rebuild_puts_a_debate_at_its_slot_and_a_watch_at_its_count() -> None:
    d = frozen.load("cut_debate_d09")
    rb = cv.rebuild(d, d["compared"][0])
    target = next(ln for ln in d["lines"] if ln["seq"] == d["compared"][0])
    assert rb.state == {"phase": target["phase"], "round": target["round"], "iteration": target["iteration"]}
    assert rb.lines[0]["author"] == "system" and rb.lines[0]["content"].startswith("ROUND 1")
    assert sum(ln["author"] == "character" for ln in rb.lines) == sum(ln["seq"] < target["seq"] for ln in d["lines"])
    w = frozen.load("cut_watch_meridian_long_a")
    rb = cv.rebuild(w, w["compared"][-1])
    assert rb.state is not None and rb.state["turnsTaken"] == sum(ln["author"] == "character" for ln in rb.lines)
    assert rb.state["turnLimit"] == rb.state["turnsTaken"] + cv.WATCH_MORE and rb.state["status"] == "paused"
    assert any(ln["kind"] == "direction" for ln in rb.lines)                  # the clinic call, a director note


# ── 6.7: sentence faithfulness ──
def test_the_factual_rule_is_fixed_in_code() -> None:
    from horizon.evals.faithfulness import factual, items

    assert factual("Yes. Most kept it, 92% of them [1]. Who's asking, and why?\nThe passage doesn't say that.") == [
        "Most kept it, 92% of them [1].", "The passage doesn't say that."]
    assert len(items(Options("faithfulness", profile="agent"))) == 10
    assert all(q["needs_two"] for q in items(Options("faithfulness", profile="agent")))


async def test_faithfulness_limit_1_on_the_fake(tmp_path: Path) -> None:
    r, out = runner(tmp_path)
    assert await r.run(Options("faithfulness", profile="agent", limit=1, yes=True)) == 0, out
    (run,) = [p for p in (tmp_path / "evals").iterdir() if p.is_dir()]
    rep = (run / "agent" / "report.md").read_text(encoding="utf-8")
    assert "## Sentence faithfulness: 1 two-passage deep turn(s)" in rep
    # NOT COUNTED follows the committed baseline: judge_sentence_supported v1 passed B4 in 8.5
    from horizon.ai.questions import bank
    from horizon.evals import judges

    validated = judges.validated("judge_sentence_supported", bank().get("judge_sentence_supported").version)
    assert ("NOT COUNTED" in rep) == (not validated)


# ── 6.3: the free runs ──
async def test_free_runs_limit_1_on_the_fake_both_profiles(tmp_path: Path) -> None:
    r, out = runner(tmp_path)
    assert await r.run(Options("conversations", set="long_one_on_one_en", limit=1, yes=True)) == 0, out
    rep = (run_dir(tmp_path) / "naive" / "report.md").read_text(encoding="utf-8")
    for who in ("agent", "naive"):
        assert f"## Free runs ({who})" in rep
    for mode in cv.MODES:
        assert f"- {mode}:" in rep
    assert "cost per turn" in rep and "repeated opener" in rep


def test_part_units_prices_and_times_no_free_runs() -> None:
    """M15 8.9: a store-backed slice of the units; the live free runs are left for the whole run, priced and timed."""
    from horizon.domain.pricing import load_price_table

    full, units_only = Options("conversations", limit=2), Options("conversations", limit=2, part="units")
    prices = load_price_table(Path(__file__).resolve().parents[3] / "seed")
    a, b = cv.Conversations().plan(full, prices, paid=True), cv.Conversations().plan(units_only, prices, paid=True)
    assert a.items == b.items and b.estimate_usd < a.estimate_usd and a.expected_s - b.expected_s == 2400


async def test_part_units_is_a_slice_without_the_free_runs(tmp_path: Path) -> None:
    r, out = runner(tmp_path)
    assert await r.run(Options("conversations", set="long_one_on_one_en", limit=1, part="units", yes=True)) == 0, out
    rep = (run_dir(tmp_path) / "naive" / "report.md").read_text(encoding="utf-8")
    assert "## Conversations: 1 of 1 unit(s)" in rep and "## Free runs" not in rep


def test_stays_is_not_counted_while_a_part_is_unvalidated_and_a_validated_row_is_added(monkeypatch: Any) -> None:
    """images-music 8.5: `judge_answers_last` failed B4 twice, so `stays` (all four) reads NOT COUNTED, and a row over
    the validated three keeps a counted figure."""
    monkeypatch.setattr("horizon.evals.judges.validated", lambda qid, v, record=None: qid != cv.ANSWERS)
    judged = {cv.VOICE: False, cv.FACT: False, cv.ANSWERS: True, cv.IN_STORY: False, "stays": False}
    rows = [{"split": "test", "lang": "en", "judged": {"agent": judged, "naive": judged}}]
    rep = cv.judged_report(rows)
    stays = next(x for x in rep if x.startswith("- stays:"))
    kept = next(x for x in rep if x.startswith("- stays (without judge_answers_last):"))
    assert "NOT COUNTED" in stays and "1/1" in stays
    assert "NOT COUNTED" not in kept and "agent 0/1" in kept
    assert cv.stays_of(judged, [cv.ANSWERS]) is True and cv.stays_of({cv.VOICE: None}, []) is None
