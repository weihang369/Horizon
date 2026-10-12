"""M8's content suites on the in-process fake (evaluation-harness "Drafter suite", "Summary suite", "Long suite",
"Long-history frozen transcripts"; persona-context design D25, D28–D31; tasks 9.6–9.7). Test mode, no network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from horizon.evals import content, planted
from horizon.evals.runner import EVALS_DIR, Options
from tests.integration.test_eval_runner import runner


def report(tmp: Path, suite: str, profile: str = "naive") -> str:
    (run,) = [p for p in (tmp / "evals").iterdir() if p.is_dir() and suite in p.name]
    return (run / profile / "report.md").read_text(encoding="utf-8")


async def test_drafter_suite_on_one_seed(tmp_path: Path) -> None:
    r, _ = runner(tmp_path)
    assert await r.run(Options("drafter", limit=2, yes=True)) == 0
    rep = report(tmp_path, "drafter")
    assert "## Drafter (2 draft(s)" in rep and "adult: " in rep and "(unvalidated)" in rep


async def test_summary_suite_on_one_item(tmp_path: Path) -> None:
    r, _ = runner(tmp_path)
    assert await r.run(Options("summary", limit=1, yes=True)) == 0
    rep = report(tmp_path, "summary")
    assert "## Summary (1 item(s)" in rep and "within 600 tokens: 1/1" in rep and "planted fact kept" in rep


async def test_long_suite_drives_the_first_lines(tmp_path: Path) -> None:
    r, _ = runner(tmp_path)
    assert await r.run(Options("long", profile="agent", limit=3, set="one_on_one_en", yes=True)) == 0
    rep = report(tmp_path, "long", "agent")
    assert "## Long: one_on_one_en (3 user lines" in rep and "reply checks:" in rep


async def test_long_refuses_any_profile_but_agent(tmp_path: Path) -> None:
    r, _ = runner(tmp_path)
    assert await r.run(Options("long", profile="naive", set="one_on_one_en", yes=True)) == 1
    assert "runs `agent` only" in report(tmp_path, "long")


async def test_transcript_smoke_writes_nothing(tmp_path: Path) -> None:
    before = sorted(p.name for p in (EVALS_DIR / "transcripts").glob("*.json"))
    r, _ = runner(tmp_path)
    assert await r.run(Options("transcript", limit=2, set="long_one_on_one_en", yes=True)) == 0
    assert sorted(p.name for p in (EVALS_DIR / "transcripts").glob("*.json")) == before


def test_transcript_loader_rejects_a_long_one_that_never_dropped(tmp_path: Path) -> None:
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"id": "t", "long": True, "turns": [{"user": "hi", "replies": [], "summary": None}]}))
    with pytest.raises(ValueError, match="never dropped"):
        content.load_transcript(p)


# ── 9.6: the committed inputs ──
def test_suite_inputs_load_with_pinned_splits() -> None:
    seeds = content.jsonl(content.DRAFTER_SEEDS)
    assert len(seeds) == 20 and {s["intent"] for s in seeds} == {"expert", "companion", "other"}
    assert sum(s["split"] == "test" for s in seeds) == 10 and len({s["world"] for s in seeds}) == 2
    items = content.jsonl(content.SUMMARY_ITEMS)
    assert len(items) == 40 and sum(i["split"] == "test" for i in items) == 20
    assert {i["language"] for i in items} == {"en", "ms", "zh"} and all(len(i["facts"]) == 3 for i in items)
    for path in sorted(content.LONG_DIR.glob("*.json")):
        s = json.loads(path.read_text(encoding="utf-8"))
        kinds = [x["kind"] for x in s["lines"]]
        assert kinds.count("fact") == 5 and kinds.count("probe") == 5 and kinds.count("wrong_claim") >= 3, path.name
        first_fact = kinds.index("fact")
        assert 2 <= first_fact and max(i for i, k in enumerate(kinds) if k == "fact") <= 9   # turns 3–10
        assert min(i for i, k in enumerate(kinds) if k == "probe") >= len(kinds) - 20       # the last 20 turns
    assert len(list((content.TRANSCRIPTS / "scripts").glob("*.json"))) == 4


def test_splits_never_change_from_the_committed_files() -> None:
    import subprocess

    for rel, key in (("evals/drafter/seeds.jsonl", "id"), ("evals/summary/items.jsonl", "id")):
        try:
            old = subprocess.run(["git", "show", f"HEAD:{rel}"], capture_output=True, text=True, check=True,
                                 cwd=EVALS_DIR.parent, encoding="utf-8").stdout
        except subprocess.CalledProcessError:
            continue   # not committed yet: nothing to compare with
        before = {json.loads(x)[key]: json.loads(x)["split"] for x in old.splitlines() if x.strip()}
        now = {i[key]: i["split"] for i in content.jsonl(EVALS_DIR.parent / rel)}
        assert all(now[k] == v for k, v in before.items() if k in now), rel


# ── 9.7: the planted generators ──
def test_planted_summary_failures_have_known_answers() -> None:
    items: list[dict[str, Any]] = [{
        "id": f"s{i}", "language": "en" if i % 2 else "ms", "lines": ["Kai: I keep a cat called Biscuit.",
                                                                      "Hana: I'll send the recipe by Friday."],
        "facts": [{"key": "Biscuit", "text": "has a cat called Biscuit"}],
        "promise": {"what": "send the recipe by Friday", "by": "Hana", "key": "recipe"},
        "summary": "Kai has a cat called Biscuit.\nHana will send the recipe by Friday."} for i in range(4)]
    out = planted.summary_planted(items, n=30)
    assert all(len(v) == 30 for v in out.values()) and len(out) == 5
    assert all(x["label"] == "yes" and x["planted"] for v in out.values() for x in v)
    assert "Biscuit" not in out["judge_summary_fact"][0]["item"]["state"]["quoted_summary"]
    assert "recipe" not in out["judge_summary_promise"][0]["item"]["state"]["quoted_summary"]
    assert "Hana will" not in out["judge_summary_who"][0]["item"]["state"]["quoted_summary"]
    assert out["judge_summary_unsupported"][0]["item"]["state"]["quoted_summary"].endswith("Marisol.")


def test_planted_reply_and_draft_failures() -> None:
    replies = [{"last": "hi", "reply": f"reply {i}", "speaker": "chr_a" if i % 2 else "chr_b",
                "language": "en" if i % 3 else "ms"} for i in range(10)]
    out = planted.reply_planted(replies, {"chr_a": "A persona", "chr_b": "B persona"}, n=30)
    assert all(len(v) == 30 for v in out.values())
    assert out["judge_flattery"][0]["item"]["state"]["quoted_reply"].startswith("What a brilliant question")
    assert out["judge_voice"][0]["item"]["state"]["quoted_persona"] == "B persona" or \
        out["judge_voice"][0]["item"]["state"]["quoted_persona"] == "A persona"
    drafts = [{"seed": f"seed {i}", "intent": "companion", "you": "Kai", "draft": {"profile": {"name": f"N{i}"}}}
              for i in range(6)]
    d = planted.draft_planted(drafts, n=30)
    assert "N0" not in d["judge_draft_fit"][0]["item"]["state"]["quoted_draft"]
    # every planted state names only fields its judge declares
    from horizon.ai.questions import bank
    for v in [*out.values(), *d.values()]:
        for x in v[:1]:
            assert set(x["item"]["state"]) <= set(bank().get(x["question_id"]).state), x["question_id"]


async def test_drafter_suite_counts_a_draft_that_stays_broken(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The paid run's first finding: a draft one `}` short, repeated word for word by C7's retry, is a measured
    failure in the report, not a crash that loses the run."""
    from horizon.gateway import fake

    broken = {"seed": "x", "intent": "expert", "valid": True, "content": '{"profile":{"name":"A"', "finish_reason": "stop"}
    monkeypatch.setattr(fake, "load_canned", lambda name: ("profile", [broken]))
    r, _ = runner(tmp_path)
    assert await r.run(Options("drafter", limit=1, yes=True)) == 0
    rep = report(tmp_path, "drafter")
    assert "valid draft after C7's one retry: 0/1" in rep and "The draft is missing" in rep   # D33 closed the JSON
