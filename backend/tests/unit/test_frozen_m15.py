"""The frozen transcripts of layer 3 (images-music design D10; evaluation-harness "Frozen transcripts for layer 3";
task 5.1). Committed files only, no network."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from horizon.evals import frozen
from horizon.evals.runner import EVALS_DIR

ADDED = ("compared",)


def test_count_and_shape() -> None:
    ts = frozen.load_all()
    modes = Counter(t["mode"] for t in ts)
    kinds = Counter(frozen.kind_of(t) for t in ts)
    assert kinds["kept"] == 4 and kinds["cut"] == 9                       # 13 now; the 7 short ones after task 8.4
    assert all(modes[m] <= n for m, n in frozen.EXPECTED.items()) and set(modes) <= set(frozen.EXPECTED)
    if len(ts) == 20:
        assert modes == Counter(frozen.EXPECTED)
    assert all(8 <= len(t["compared"]) <= 12 for t in ts), [(t["id"], len(t["compared"])) for t in ts]
    assert sum(t["long"] for t in ts if t.get("long")) == 4               # the "past one drop" four
    assert all(isinstance(t["memories"], dict) and set(t["memories"]) == set(t["cast"]) for t in ts)


def test_cut_from_a_committed_history_line_for_line() -> None:
    for tid, source, first, last in frozen.CUTS:
        doc = json.loads((frozen.TRANSCRIPTS / f"{tid}.json").read_text(encoding="utf-8"))
        assert doc == frozen.cut(tid, source, first, last)                # a re-cut writes the same file
        assert doc["source"] == {"history": source, "id": doc["source"]["id"], "from_seq": first, "to_seq": last}
        src = {ln["seq"]: ln for ln in json.loads((EVALS_DIR / source).read_text(encoding="utf-8"))["lines"]}
        for ln in doc["lines"]:
            mine = {k: v for k, v in ln.items() if k not in ADDED}
            theirs = {**src[ln["seq"]]}
            theirs.setdefault("summary_upto", None)
            theirs.setdefault("summary", None)
            assert mine == theirs, (tid, ln["seq"])
        assert [ln["seq"] for ln in doc["lines"]] == sorted(s for s in src if s <= last)


def test_debates_come_from_the_debate_suites_dev_side() -> None:
    from horizon.evals.debate_suites import debate_split, histories

    hs = histories()
    sp = debate_split([h["id"] for h in hs], min(8, max(1, round(len(hs) * 2 / 3))))
    used = [json.loads((frozen.TRANSCRIPTS / f"{tid}.json").read_text(encoding="utf-8"))["source"]["id"]
            for tid, source, *_ in frozen.CUTS if source.startswith("debates/")]
    assert len(used) == 4 and all(sp[d] == "dev" for d in used)


def test_watch_cuts_two_from_meridian_long_and_no_free_run() -> None:
    sources = [s for _, s, *_ in frozen.CUTS if s.startswith("watch/")]
    assert len(sources) == 5 and sources.count("watch/meridian_long.json") == 2
    assert not any("freerun" in s for s in sources)


def test_the_split_is_a_third_per_mode_and_fixed_by_the_ids() -> None:
    ts = frozen.load_all()
    by_mode: dict[str, list[str]] = {}
    for t in ts:
        by_mode.setdefault(t["mode"], []).append(t["id"])
    for ids in by_mode.values():
        assert sum(t["split"] == "test" for t in ts if t["id"] in ids) == max(1, round(len(ids) / 3))
    assert frozen.split(by_mode) == {t["id"]: t["split"] for t in ts}


# ── 5.2: the 7 short scripts ──
def short_scripts() -> list[dict[str, Any]]:
    return [s for p in sorted((frozen.TRANSCRIPTS / "scripts").glob("*.json"))
            if (s := json.loads(p.read_text(encoding="utf-8"))).get("short")]


def test_the_short_scripts_load_with_their_labels() -> None:
    ss = short_scripts()
    assert Counter(s["mode"] for s in ss) == Counter({"one_on_one": 4, "group": 3})
    assert {s["world"] for s in ss if s["mode"] == "group"} == {"wld_seedMeridian", "wld_seedSunnyHollow"}
    ones = {s["cast"][0] for s in ss if s["mode"] == "one_on_one"}
    kept = {frozen.load(k)["cast"][0] for k in frozen.KEPT if k.startswith("long_one_on_one")}
    assert len(ones) == 4 and not ones & kept                             # the four seed characters without a long 1:1
    assert all(8 <= len(s["lines"]) <= 12 for s in ss)
    lines = [ln for s in ss for ln in s["lines"]]
    assert sum(ln.get("lang", "en") != "en" for ln in lines) >= 10
    assert sum(ln["kind"] == "wrong_claim" for ln in lines) >= 10
    docs = [s for s in ss if any(ln["kind"] == "docs" for ln in s["lines"])]
    assert Counter(s["mode"] for s in docs) == Counter({"one_on_one": 2, "group": 1})
    assert any(ln.get("covered") is False for s in docs for ln in s["lines"])   # one question the documents don't cover
    assert all(ln["kind"] in ("filler", "fact", "wrong_claim", "docs") for ln in lines)   # no safety items
