"""M11's offline evaluation (debate tasks 8–9; design D17–D22): the sets are built by the live code, deterministically,
and every report runs on fixture answers. No network: the fake provider answers everything."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from horizon.ai.decider import Choice
from horizon.evals import suites, watch_suites
from horizon.evals.runner import EVALS_DIR, Options, RunEnv
from tests.conftest import Api

DATASETS = EVALS_DIR / "datasets"


def env_for(api: Api, tmp: Path, opts: Options) -> RunEnv:
    run_dir = tmp / "evals" / "run-1" / opts.profile
    run_dir.mkdir(parents=True, exist_ok=True)
    return RunEnv(rt=api.rt, opts=opts, store=None, run_dir=run_dir, max_usd=1.0)


def decision_bodies(api: Api, key: str) -> list[dict[str, Any]]:
    assert api.rt.fake is not None
    return [b for b in (json.loads(r.content) for r in api.rt.fake.requests if r.url.path.endswith("/alpha/decisions"))
            if key in b["questions"]]


def load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def who_next_builder() -> Any:
    sys.path.insert(0, str(DATASETS / "who_speaks"))
    return load("who_next_build", DATASETS / "who_speaks" / "next.py")


# ── 8.1: who_next ──
def test_the_who_next_builder_is_deterministic_and_uses_the_live_state() -> None:
    nxt = who_next_builder()
    rows = nxt.build_next(nxt.profiles())
    assert rows == suites.load_dataset(DATASETS / "who_speaks" / "who_next.jsonl")
    assert nxt.check(rows) == []
    assert sum(r["split"] == "test" for r in rows) >= 20
    for r in rows:
        st = r["item"]["state"]
        assert "last_spoke" not in json.dumps(st)                          # v3: no turns-since in what Jev sees
        assert st["quoted_latest"].split(": ", 1)[0] not in [c["name"] for c in st["quoted_cast"]]
        q = suites.item_question(r)
        assert isinstance(q, Choice) and "none" not in q.options and sorted(q.options) == sorted(r["label"]["candidates"])


# ── 8.3: judge_starts_new ──
def test_the_starts_new_set_is_built_from_m10s_free_runs() -> None:
    sn = load("starts_new_build", DATASETS / "judges" / "starts_new.py")
    rows = sn.build()
    assert rows == suites.load_dataset(DATASETS / "judges" / "judge_starts_new.jsonl")
    assert sn.check(rows) == []
    steered = [r for r in rows if r.get("steered")]
    assert len(steered) == 7 and not any(r["planted"] for r in steered)
    st = rows[0]["item"]["state"]
    assert set(st) == {"quoted_premise", "quoted_recent", "quoted_line"} and len(st["quoted_recent"].split("\n")) >= 6


def steered_msg(i: int, cid: str, text: str, steer: bool) -> dict[str, Any]:
    rows = [{"id": "talk_finished", "action": "steer"}] if steer else []
    return {"id": f"m{i}", "author": {"type": "character", "characterId": cid}, "content": text,
            "trace": {"routing": {}, "system1": {"questions": rows}}}


def test_steered_lines_are_listed_with_their_judge_p(monkeypatch: pytest.MonkeyPatch) -> None:
    """The evaluation-harness scenario "Steered lines are listed", on fixture answers."""
    from horizon.evals import judges

    monkeypatch.setattr(judges, "validated", lambda qid, version, record=None: False)   # whatever the record says
    msgs = [steered_msg(i, f"chr_{i % 3}", f"Line {i}.", i in (4, 9, 13)) for i in range(15)]
    text = "\n".join(watch_suites.freerun_report("watch", msgs, 0, {"m4": 0.2, "m9": 0.8, "m13": 0.1}))
    assert "the steer fired on 3/15" in text
    assert "steered lines that start something new: 2/3 (67%) (M10: 0 of 7" in text
    assert "(unvalidated)" in text                         # until B4 records the judge's pass
    listed = [x for x in text.splitlines() if "STEERED" in x]
    assert [x.split("(p ")[1][:4] for x in listed] == ["0.20", "0.80", "0.10"]
    assert "starts nothing new): Line 9." in listed[1] and "starts something new): Line 4." in listed[0]


async def test_the_steered_line_is_judged_with_its_premise_and_six_lines_before(api: Api, tmp_path: Path) -> None:
    await api.set_key()
    msgs = [steered_msg(i, "chr_seedHana", f"Line {i}.", i == 8) for i in range(9)]
    env = env_for(api, tmp_path, Options("freerun", profile="agent", mode="watch"))
    got = await watch_suites.judge_steered(env, "A rainy Sunday.", msgs, watch_suites.seed_profiles())
    assert list(got) == ["m8"]
    (body,) = decision_bodies(api, "judge_starts_new")
    st = body["state"]
    assert st["quoted_premise"] == "A rainy Sunday."
    assert st["quoted_recent"].splitlines() == [f"Hana Morisaki: Line {i}." for i in range(2, 8)]
    assert st["quoted_line"] == "Hana Morisaki: Line 8."


# ── 8.4: the recap judge gets the premise ──
async def test_a_detail_from_the_premise_reaches_the_unsupported_judge(api: Api, tmp_path: Path,
                                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    """The scenario "A detail from the premise", with the M10 recap item `recap-sunnyhollow-010`."""
    from horizon.evals.content import Summary
    from horizon.gateway.fake import load_canned

    await api.set_key()
    monkeypatch.setattr(watch_suites, "RECAP_POINTS", {"sunnyhollow": (10,)})
    assert [i["id"] for i in watch_suites.recap_items()] == ["recap-sunnyhollow-010"]
    assert api.rt.fake is not None
    purpose, canned = load_canned("episode-recaps")
    api.rt.fake.set_canned(purpose, canned)
    s = Summary()
    opts = Options("summary", set="recaps")
    await s.run(env_for(api, tmp_path, opts), s.plan(opts, api.rt.prices, paid=True))
    (body,) = decision_bodies(api, "judge_summary_unsupported")
    assert "flower festival" in body["state"]["quoted_premise"]
    assert "quoted_premise" in body["questions"]["judge_summary_unsupported"]["instructions"]


# ── 9.1: debate-history ──
def test_debate_history_refuses_to_overwrite_a_committed_history(tmp_path: Path,
                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    """The scenario "Refused regeneration": the refusal is checked before the plan, the prompt and any call."""
    from horizon.evals import debate_suites as ds

    monkeypatch.setattr(ds, "DEBATES_DIR", tmp_path)
    (tmp_path / "d01.json").write_text("{}", encoding="utf-8")
    assert "d01" in (ds.DebateHistory().refuse(Options("debate-history")) or "")
    assert ds.DebateHistory().refuse(Options("debate-history", force=True)) is None


async def test_the_runner_refuses_a_committed_history_before_any_call(tmp_path: Path,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    from horizon.evals import debate_suites as ds
    from horizon.evals.runner import Runner
    from tests.conftest import make_config

    monkeypatch.setattr(ds, "DEBATES_DIR", tmp_path)
    (tmp_path / "d01.json").write_text("{}", encoding="utf-8")
    said: list[str] = []
    runner = Runner(make_config(tmp_path, test_mode=True))
    runner.out = said.append  # type: ignore[method-assign]
    code = await runner.run(Options("debate-history", set="d01", yes=True))
    assert code == 2 and "--force" in said[0] and not any(x.startswith("plan:") for x in said)


def test_the_scripts_follow_d21s_mix() -> None:
    from collections import Counter

    from horizon.evals import debate_suites as ds

    def shape(s: dict[str, Any]) -> tuple[str, str, int, int]:
        cfg = s["config"]
        return cfg["format"], cfg["roundsPreset"], len((cfg.get("sides") or {}).get("prop") or []), len(s["cast"])

    assert Counter(shape(s) for s in ds.scripts()) == Counter({
        ("two_sided", "standard", 2, 4): 8, ("two_sided", "standard", 3, 5): 2, ("two_sided", "quick", 2, 4): 2,
        ("panel", "standard", 0, 4): 1})
    assert {s["world"] for s in ds.scripts()} == {"wld_seedMeridian", "wld_seedSunnyHollow"}
    assert len({s["config"]["motion"] for s in ds.scripts()}) == 13
    assert sum(ds.expected_arguments(s) for s in ds.scripts()) == 154                   # D23's ≈ 154 arguments
    prof = ds.profiles()
    for s in ds.scripts():                       # a side's members differ in field (D21)
        for side in (s["config"].get("sides") or {}).values():
            roles = [prof[c]["role"] for c in side]
            assert len(set(roles)) == len(roles)


def test_the_eval_cast_is_valid_and_never_seed(api: Api) -> None:
    from horizon.config import REPO_ROOT
    from horizon.evals import debate_suites as ds

    wires = ds.cast_wires(REPO_ROOT / "seed")
    assert [w["id"] for w in wires] == ["chr_evalDaniel", "chr_evalSofia", "chr_evalAiko", "chr_evalBram"]
    for w in wires:
        assert api.rt.schema.errors("Character", w) == [], w["id"]
        assert not w["isSeed"] and w["status"] == "approved" and "themeSongId" not in w
        tag = "Eval" + w["id"].removeprefix("chr_eval")
        assert all(r["assetId"].endswith(tag) for r in w["emotions"].values())
    assert not (REPO_ROOT / "seed" / "characters" / "chr_evalDaniel.json").exists()


async def test_a_test_mode_history_on_the_fake(api: Api, tmp_path: Path) -> None:
    from horizon.evals import debate_suites as ds

    await api.set_key()
    opts = Options("debate-history", limit=1, set="d09")
    s = ds.DebateHistory()
    env = env_for(api, tmp_path, opts)
    res = await s.run(env, s.plan(opts, api.rt.prices, paid=False))
    assert res.status == "ok"
    doc = json.loads((env.run_dir / "d09.json").read_text(encoding="utf-8"))
    args = ds.arguments(doc)
    assert len(args) == 15 and {a["phase"] for a in args} == {"opening", "rebuttal", "closing"}
    assert [a["side"] for a in args[:5]] == ["prop", "opp", "prop", "opp", "prop"]          # 3 v 2 runs P O P O P
    assert {"Daniel Osei", "Sofia Brandt"} <= {a["name"] for a in args}
    assert doc["motion"] == "This house would make voting compulsory" and doc["sides"]["prop"][2] == "chr_evalDaniel"


# ── 9.2: debate-plant ──
def fixture_history(did: str, phases: tuple[str, ...] = ("opening", "rebuttal", "closing")) -> dict[str, Any]:
    lines = []
    seq = 2
    for phase in phases:
        for k, (side, cid, name) in enumerate([("prop", "chr_a", "Ana"), ("opp", "chr_b", "Ben"),
                                              ("prop", "chr_c", "Cy"), ("opp", "chr_d", "Di")]):
            lines.append({"seq": seq, "kind": "argument", "phase": phase, "round": phases.index(phase) + 1,
                          "iteration": 1, "side": side, "speaker": cid, "name": name,
                          "text": f"{name} {phase} argument {k}."})
            seq += 1
        seq += 1
    return {"schemaVersion": 1, "id": did, "mode": "debate", "world": "wld_seedMeridian",
            "cast": ["chr_a", "chr_b", "chr_c", "chr_d"], "language": "en", "motion": "This house would test",
            "format": "two_sided", "roundsPreset": "standard", "phases": list(phases),
            "sides": {"prop": ["chr_a", "chr_c"], "opp": ["chr_b", "chr_d"]}, "lines": lines}


async def test_which_side_is_weak(api: Api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The scenario "Which side is weak": prop on even-numbered debates, opp on odd; that side's rebuttals and
    closings are rewritten (canned here), its openings and the other side untouched."""
    from horizon.evals import debate_suites as ds

    assert (ds.weak_side("d02"), ds.weak_side("d03")) == ("prop", "opp")
    await api.set_key()
    assert api.rt.fake is not None
    api.rt.fake.set_canned(ds.PLANT_PURPOSE, [{"content": "'I said it at the start and I say it again.'"}])
    hs = [fixture_history("d02"), fixture_history("d11", ("opening", "closing"))]
    monkeypatch.setattr(ds, "histories", lambda root=None: hs)
    opts = Options("debate-plant", limit=2)
    s = ds.DebatePlant()
    env = env_for(api, tmp_path, opts)
    res = await s.run(env, s.plan(opts, api.rt.prices, paid=False))
    assert [(r["debate"], r["weak"], r["rewritten"]) for r in res.rows] == [("d02", "prop", 4), ("d11", "opp", 2)]
    doc = json.loads((env.run_dir / "planted" / "d02.json").read_text(encoding="utf-8"))
    planted = [x for x in doc["lines"] if x.get("planted")]
    assert {(x["side"], x["phase"]) for x in planted} == {("prop", "rebuttal"), ("prop", "closing")}
    assert all(x["text"] == "I said it at the start and I say it again." and x["original"] for x in planted)
    assert doc["planted"]["weak"] == "prop" and len(doc["planted"]["rewritten"]) == 4
    body = next(json.loads(r.content) for r in api.rt.fake.requests if r.url.path.endswith("/chat/completions"))
    assert "Their opening argument:\n'Ana opening argument 0.'" in body["messages"][1]["content"]
    assert "same voice, same length" in body["messages"][0]["content"]


# ── 9.3: the member slice ──
SOFIA, AMARA, VICTOR, MEI, DANIEL = "chr_evalSofia", "chr_seedAmara", "chr_seedVictor", "chr_seedMei", "chr_evalDaniel"


def meridian_history(did: str, prop: list[str], opp: list[str],
                     phases: tuple[str, ...] = ("opening", "rebuttal", "closing")) -> dict[str, Any]:
    """A fixture history in the committed format, with real cast ids so the live state builder can read profiles."""
    from horizon.evals import debate_suites as ds

    prof = ds.profiles()
    order = [c for pair in zip(prop + [""] * 3, opp + [""] * 3, strict=False) for c in pair if c][: len(prop + opp)]
    side_of = {**dict.fromkeys(prop, "prop"), **dict.fromkeys(opp, "opp")}
    lines, seq = [], 2
    for r, phase in enumerate(phases, 1):
        for cid in order:
            lines.append({"seq": seq, "kind": "argument", "phase": phase, "round": r, "iteration": 1,
                          "side": side_of[cid], "speaker": cid, "name": prof[cid]["name"],
                          "text": f"{cid} on {phase}."})
            seq += 1
        seq += 1
    return {"schemaVersion": 1, "id": did, "mode": "debate", "world": "wld_seedMeridian", "cast": order,
            "language": "en", "motion": "This house would ban homework", "format": "two_sided",
            "roundsPreset": "standard", "phases": list(phases), "sides": {"prop": prop, "opp": opp}, "lines": lines}


def test_the_member_slice_is_cut_with_the_live_state() -> None:
    from horizon.evals import debate_suites as ds

    mb = load("debate_member_build", DATASETS / "debate_member" / "build.py")
    h = meridian_history("d01", [SOFIA, AMARA], [VICTOR, MEI])
    h3 = meridian_history("d09", [VICTOR, MEI, DANIEL], [AMARA, SOFIA])
    natural = ds.natural_member_slots(h)
    assert [(s["phase"], s["side"], s["eligible"]) for s in natural] == [
        ("rebuttal", "prop", [SOFIA, AMARA]), ("rebuttal", "opp", [VICTOR, MEI]),
        ("closing", "prop", [SOFIA, AMARA]), ("closing", "opp", [VICTOR, MEI])]
    assert [len(s["eligible"]) for s in ds.natural_member_slots(h3)] == [3, 2, 2, 3, 2, 2]   # P O P, twice
    first = natural[0]["seq"]
    labels = {f"d01#{first}": ([AMARA], True), f"d01#{natural[1]['seq']}": ([VICTOR, MEI], False)}
    variants = [("d01", first, "Homework stops children walking to school: the streets are the issue.", SOFIA, "en"),
                ("d01", first, "Kerja rumah menyebabkan kesesakan jalan raya pada waktu pagi.", SOFIA, "ms")]
    rows = mb.build([h, h3], ds.profiles(), labels, variants, tests=1)
    assert rows == mb.build([h, h3], ds.profiles(), labels, variants, tests=1)          # deterministic
    assert [r["label"]["acceptable"] for r in rows] == [[AMARA], [VICTOR, MEI], [SOFIA], [SOFIA]]
    assert [r["label"]["single"] for r in rows] == [True, False, True, True]
    assert all(r["label"]["fixed"] == r["label"]["candidates"][0] for r in rows)
    live = ds.cut_state(ds.cut_request(h, natural[0], ds.profiles()))[0]
    assert rows[0]["item"]["state"] == live and "last_spoke" not in json.dumps(live)
    assert rows[0]["item"]["side"] == "Proposition" and rows[0]["question_id"] == "member_rebuttal"
    variant = rows[2]["item"]["state"]["quoted_arguments"]["last_opposing"]
    assert variant == "Mei Tanaka-Ruiz: Homework stops children walking to school: the streets are the issue."
    assert rows[3]["lang"] == "ms" and "(written variant)" in rows[3]["source"]
    q = suites.item_question(rows[0])
    assert isinstance(q, Choice) and sorted(q.options) == sorted([SOFIA, AMARA])
    assert "Proposition speakers" in q.instructions
    assert mb.check(rows) != []                    # the real counts (90, 45 single, the languages) aren't met here


# ── 9.4: the member policy ──
def member_row(split: str, ok: str, jev: str, single: bool = True, lang: str = "en") -> dict[str, Any]:
    return {"question_id": "member_rebuttal", "split": split, "lang": lang, "answer": jev, "confidence": 0.9,
            "probabilities": {jev: 0.9}, "label": {"candidates": ["chr_a", "chr_b"], "acceptable": [ok],
                                                    "single": single, "fixed": "chr_a"}}


def test_a_pass_needs_both_measures() -> None:
    """The scenario: 0.85 inside the set, but only 8 points above fixed order on the single-answer items → FAIL."""
    from horizon.evals import who_policies as wp

    dev = [member_row("dev", "chr_a", "chr_a") for _ in range(10)]
    test = ([member_row("test", "chr_a", "chr_a") for _ in range(77)]
            + [member_row("test", "chr_b", "chr_b") for _ in range(8)]
            + [member_row("test", "chr_b", "chr_a") for _ in range(15)])
    text = "\n".join(wp.member_report(dev + test))
    assert "inside the set 85/100 = 0.85" in text and "→ PASS" in text.splitlines()[1]
    assert "difference +0.08" in text and "member check FAIL" in text.splitlines()[0]
    assert "random-pick baseline: 0.50" in text
    good = ([member_row("test", "chr_a", "chr_a") for _ in range(55)]
            + [member_row("test", "chr_b", "chr_b") for _ in range(30)]
            + [member_row("test", "chr_b", "chr_a") for _ in range(15)])
    assert "member check PASS" in wp.member_report(dev + good)[0]


def test_below_the_floor_the_member_is_the_fixed_order() -> None:
    from horizon.ai.decider import ChoiceAnswer
    from horizon.evals import who_policies as wp

    lab = {"candidates": ["chr_a", "chr_b"], "acceptable": ["chr_b"], "single": True, "fixed": "chr_a"}
    assert wp.member_answer(ChoiceAnswer("chr_b", confidence=0.7), lab, 0.6) == "chr_b"
    assert wp.member_answer(ChoiceAnswer("chr_b", confidence=0.5), lab, 0.6) == "chr_a"
    assert wp.member_answer(None, lab, 0.6) == "chr_a"


# ── 9.5: the debate emotion slice ──
def emotion_slice(tests: int = 1) -> list[dict[str, Any]]:
    from horizon.evals import debate_suites as ds

    em = load("emotion_debate_build", DATASETS / "emotion" / "build_debate.py")
    h = meridian_history("d01", [SOFIA, AMARA], [VICTOR, MEI])
    for x in h["lines"]:
        x["emotion"] = "thinking" if x["speaker"] == AMARA else "neutral"
    seqs = [s["seq"] for s in ds.slots(h)]
    lines = [("d01", seqs[k], ["thinking"], False) for k in range(4, 12)]
    openings = [("d01", seqs[k], ["neutral"], True) for k in range(4)]
    return list(em.build([h], ds.profiles(), lines, openings, tests=tests))


def test_the_debate_emotion_slice_is_cut_as_live_asks() -> None:
    rows = emotion_slice()
    assert [r["question_id"] for r in rows].count("emotion_debate_opening") == 4
    first = next(r for r in rows if r["question_id"] == "emotion_debate_opening")
    st = first["item"]["state"]
    assert set(st) <= {"mode", "side", "quoted_user", "quoted_cast", "quoted_motion"}   # only what it declares
    assert st["quoted_motion"] == "This house would ban homework" and st["side"] == "prop"
    line = next(r for r in rows if r["question_id"] == "emotion_line" and r["source"].endswith("#9"))
    assert line["item"]["name"] == "Amara Okafor" and line["label"]["previous"] == "thinking"   # her opening face
    assert line["item"]["state"]["quoted_latest"].startswith("Victor Hale: ")   # the argument just made
    q = suites.item_question(line)
    assert isinstance(q, Choice) and "Amara" in q.instructions


async def test_the_slice_is_scored_alone(api: Api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The scenario "The slice is scored alone": the debate slice's floor and accuracy are reported apart, and the
    other emotion items' report doesn't include it."""
    await api.set_key()
    root = tmp_path / "datasets"
    (root / "emotion").mkdir(parents=True)
    m9 = suites.load_dataset(DATASETS / "emotion" / "emotion.jsonl")
    keep = [r for r in m9 if r["split"] == "dev"][:4] + [r for r in m9 if r["split"] == "test"][:3]
    debate = emotion_slice(tests=3)
    for name, rows in (("emotion.jsonl", keep), ("emotion_debate.jsonl", debate)):
        (root / "emotion" / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                             encoding="utf-8")
    monkeypatch.setattr(suites, "DATASETS", root)
    d = suites.Decisions()
    opts = Options("decisions")
    res = await d.run(env_for(api, tmp_path, opts), d.plan(opts, api.rt.prices, paid=True))
    heads = [x for x in res.summary if x.startswith("## Emotion")]
    assert len(heads) == 2 and heads[1].startswith("## Emotion (the debate slice, its own floor): floor ")
    assert {r["kind"] for r in res.rows if r["id"].startswith("emd")} == {"debate"}


# ── 9.6: the debate-quality judge ──
def test_the_judge_sets_plant_by_rule() -> None:
    from horizon.evals import debate_suites as ds

    dq = load("debate_quality_build", DATASETS / "judges" / "debate_quality.py")
    hs = [meridian_history("d01", [SOFIA, AMARA], [VICTOR, MEI]), meridian_history("d02", [DANIEL, AMARA], [MEI, SOFIA])]
    real_keeps = [("d01", 7, "no")]
    sets = dq.build(hs, real_keeps, [("d02", 12, "no")], n=4)
    keeps, engages = sets[ds.KEEPS], sets[ds.ENGAGES]
    assert [r["planted"] for r in keeps] == [False, True, True, True, True]
    real = keeps[0]
    assert real["item"]["side"] == "Proposition" and real["item"]["state"]["quoted_argument"].startswith("Sofia Brandt:")
    first = keeps[1]                     # d01's first unused rebuttal (Victor, opp) asked as the Proposition
    assert first["source"].startswith("debate:d01#8") and first["item"]["side"] == "Proposition"
    assert keeps[2]["source"].startswith("debate:d02#7")                  # the debates take turns
    plant = engages[1]
    assert plant["item"]["state"]["quoted_argument"].endswith("on opening.")      # the speaker's own opening
    assert plant["label"] == "yes" and plant["item"]["state"]["quoted_previous"].startswith("Victor Hale: ")
    q = suites.item_question(first)
    assert "Proposition's position" in q.instructions
    assert dq.check(sets) != []          # 30 + 30 each only on the real histories


async def test_an_unvalidated_judge_does_not_count(api: Api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The scenario "An unvalidated judge doesn't count": the rates are printed but marked not counted."""
    from horizon.evals import debate_suites as ds
    from horizon.evals import judges

    await api.set_key()
    h = meridian_history("d01", [SOFIA, AMARA], [VICTOR, MEI])
    monkeypatch.setattr(ds, "histories", lambda root=None: [h])
    monkeypatch.setattr(judges, "validated", lambda qid, version, record=None: False)   # whatever the record says
    opts = Options("debate-quality")
    s = ds.DebateQuality()
    res = await s.run(env_for(api, tmp_path, opts), s.plan(opts, api.rt.prices, paid=False))
    assert len(res.rows) == 12 + 8                    # every argument keeps its side; rebuttals and closings engage
    text = "\n".join(res.summary)
    assert text.count("NOT COUNTED") == 2 and "(naive column)" in text
    monkeypatch.setattr(judges, "validated", lambda qid, version, record=None: True)
    assert "NOT COUNTED" not in "\n".join(ds.quality_report(res.rows, "agent"))


# ── 9.7: the debate suite ──
def scored(debate: str, version: str, swapped: bool, prop: float, opp: float, strong: str | None = None,
           split: str = "test") -> dict[str, Any]:
    bars = [{"subjectId": s, "criterionId": c, "value": v} for s, v in (("prop", prop), ("opp", opp))
            for c in ("evidence", "rebuttal", "clarity", "persuasion")]
    return {"debate": debate, "version": version, "swapped": swapped, "split": split, "strong": strong, "bars": bars,
            "means": {"prop": prop, "opp": opp}, "failure": None}


def test_swap_flips_are_counted_apart_from_ties() -> None:
    """The scenario: one swapped item goes Proposition → Opposition, another Proposition → too close."""
    from horizon.evals import debate_suites as ds

    rows = [scored("d01", "balanced", False, 7.0, 5.0), scored("d01", "balanced", True, 5.0, 7.0),
            scored("d02", "balanced", False, 7.0, 5.0), scored("d02", "balanced", True, 6.2, 6.0),
            scored("d03", "balanced", False, 7.0, 5.0), scored("d03", "balanced", True, 7.0, 5.0)]
    text = "\n".join(ds.measures(rows, 0.5))
    assert "winner flips 1/3" in text and "FLIP d01 balanced: prop → opp" in text
    assert "changes to or from too close, reported apart: 1/3" in text and "d02 balanced: prop → too close" in text


def test_the_margin_rule() -> None:
    from horizon.evals import debate_suites as ds

    dev = [scored("d01", "planted", False, 7.0, 6.2, "prop", "dev"), scored("d02", "planted", False, 5.0, 7.5, "opp",
                                                                            "dev"),
           scored("d03", "balanced", False, 6.0, 6.6, None, "dev"), scored("d04", "balanced", False, 6.0, 6.1, None,
                                                                            "dev")]
    sel = ds.choose_margin(dev)
    # the planted gaps are 0.8 and 2.5, the balanced 0.6 and 0.1: at 0.75 every balanced item is too close, and at
    # 1.0 a planted one is, so 0.5 is the largest margin that keeps both rules
    assert sel["margin"] == 0.5 and sel["found"]
    assert [m for m, g in sel["grid"].items() if g["ok"]] == [0.0, 0.25, 0.5]
    wrong = ds.choose_margin([scored("d01", "planted", False, 6.0, 7.0, "prop", "dev")])
    assert wrong["margin"] == 0.5 and not wrong["found"]                  # none qualifies: 0.5 stays, a finding


def fixture_suite(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    from horizon.evals import debate_suites as ds

    hs = [meridian_history(f"d{n:02d}", [SOFIA, AMARA], [VICTOR, MEI]) for n in range(1, 4)]
    plants = {h["id"]: {**h, "planted": {"weak": ds.weak_side(h["id"]), "rewritten": []}} for h in hs}
    panel = {**meridian_history("d13", [SOFIA, AMARA], [VICTOR, MEI]), "format": "panel", "sides": None}
    for x in panel["lines"]:
        x["side"] = None
    monkeypatch.setattr(ds, "histories", lambda root=None: [*hs, panel])
    monkeypatch.setattr(ds, "load_planted", lambda did, root=None: plants.get(did))
    return hs


async def test_the_margin_is_tuned_on_dev_only(api: Api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The scenario: no test item's answer is read before the margin is written."""
    from horizon.evals import debate_suites as ds

    await _agent(api)
    fixture_suite(monkeypatch)
    monkeypatch.setattr(ds, "TEST_DEBATES", 2)
    opts = Options("debate", profile="agent")
    env = env_for(api, tmp_path, opts)
    order: list[tuple[str, bool]] = []
    real = ds.score_row

    async def spy(env_: Any, h: dict[str, Any], version: str, swapped: bool, split: str) -> dict[str, Any]:
        order.append((split, (env.run_dir / "margin.json").is_file()))
        return await real(env_, h, version, swapped, split)

    monkeypatch.setattr(ds, "score_row", spy)
    s = ds.DebateSuite()
    res = await s.run(env, s.plan(opts, api.rt.prices, paid=False))
    assert [sp for sp, _ in order] == ["dev"] * 4 + ["test"] * 8          # 1 dev and 2 test debates, ×2 versions ×2
    assert not any(written for sp, written in order if sp == "dev") and all(w for sp, w in order if sp == "test")
    assert res.summary[0].startswith("## Debate verdict (agent): margin ")


async def test_every_prose_and_host_item_is_printed(api: Api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The scenario "Every item is printed": all the verdicts with each noul's p, flagged or not."""
    from horizon.evals import debate_suites as ds

    await _agent(api)
    hs = fixture_suite(monkeypatch)
    monkeypatch.setattr(ds, "ARBITER_VERDICTS", 2)
    monkeypatch.setattr(ds, "USER_VERDICTS", 1)
    monkeypatch.setattr(ds, "BRIDGES", 3)
    env = env_for(api, tmp_path, Options("debate", profile="agent"))
    lines = await ds.DebateSuite.checks(env, hs, {h["id"]: "test" for h in hs})
    prose_head = next(x for x in lines if x.startswith("## Verdict prose checks"))
    host_head = next(x for x in lines if x.startswith("## Host bridge checks"))
    assert "/4 flagged" in prose_head and "/3 flagged" in host_head    # 2 Arbiter + 1 You decide + the panel
    items = [x for x in lines if x.startswith("- ok ") or x.startswith("- FLAGGED ")]
    assert len(items) == 7
    assert sum(1 for x in lines if "judge_host_partisan" in x) == 3
    assert any("judge_verdict_point_unsaid" in x and "p " in x for x in lines)


async def _agent(api: Api) -> None:
    from tests.sessions.kit import API

    await api.set_key()
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": "agent"})).status_code == 204


# ── 9.8: latency --part debate ──
def test_a_slow_api_is_kept() -> None:
    """The scenario: 9 of the 30 requests take longer than 500 ms → the check fails and states the p90 to set."""
    from horizon.evals import debate_suites as ds

    rows = [{"s_ms": 2.0, "l_ms": 420.0, "tokens": 2400}] * 21 + [{"s_ms": 2.0, "l_ms": 640.0, "tokens": 2400}] * 9
    text = "\n".join(ds.plan_timing_report(rows))
    assert "9/30 past 500 ms (30%" in text and "→ FAIL" in text
    assert "set timeoutsMs.decision.debate_plan to the measured p90, 642 ms" in text
    assert "→ PASS" in ds.plan_timing_report(rows[:21] + rows[21:23])[0]                 # 2 of 23 is under 10 %


async def test_the_plan_timing_asks_the_live_request(api: Api, tmp_path: Path) -> None:
    from horizon.evals import debate_suites as ds

    await _agent(api)
    h = meridian_history("d01", [SOFIA, AMARA], [VICTOR, MEI])
    reqs = [(f"x{k}", ds.cut_request(h, sl, ds.profiles())) for k, sl in enumerate(ds.natural_member_slots(h))]
    rows = await ds.plan_timing(env_for(api, tmp_path, Options("latency", profile="agent", part="debate")), reqs)
    assert len(rows) == 4 and all(r["s_ms"] >= 0 and r["l_ms"] >= 0 and r["tokens"] > 0 for r in rows)
    bodies = decision_bodies(api, "member_rebuttal")
    assert len(bodies) == 2 and set(bodies[0]["questions"]) == {
        "member_rebuttal", f"emotion_line:{SOFIA}", f"emotion_line:{AMARA}"}


async def test_bridges_are_kept(api: Api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The scenario: after the timing run, its bridges and verdicts are in the store, and the debate suite's prose and
    host checks read them without a new call."""
    from horizon.evals import debate_suites as ds
    from horizon.evals.runner import Result

    await _agent(api)
    hs = [meridian_history(f"d{n:02d}", [SOFIA, AMARA], [VICTOR, MEI]) for n in range(1, 4)]
    monkeypatch.setattr(ds, "histories", lambda root=None: hs)
    monkeypatch.setattr(ds, "member_dev_requests", lambda n: [])
    monkeypatch.setattr(ds, "ARBITER_VERDICTS", 2)
    monkeypatch.setattr(ds, "USER_VERDICTS", 0)
    monkeypatch.setattr(ds, "BRIDGES", 4)
    env = env_for(api, tmp_path, Options("latency", profile="agent", part="debate"))
    assert api.rt.gateway.store is None                                   # latency never reads the store
    res = Result()
    await ds.debate_timing(env, 30, res)
    assert api.rt.gateway.store is None
    text = "\n".join(res.summary)
    assert "## Host bridges: " in text and "/4 on time" in text and "## Arbiter verdicts:" in text
    assert [r["part"] for r in res.rows].count("verdict") == 2
    assert api.rt.fake is not None
    chats = sum(1 for r in api.rt.fake.requests if r.url.path.endswith("/chat/completions"))
    api.rt.gateway.store = ds.eval_store(env)                           # the debate suite's run reads the store
    try:
        await ds.DebateSuite.checks(env, hs, {h["id"]: "test" for h in hs})
    finally:
        api.rt.gateway.store = None
    assert sum(1 for r in api.rt.fake.requests if r.url.path.endswith("/chat/completions")) == chats   # no new call


# ── 9.9: freerun --mode debate ──
async def test_a_member_choice_report(api: Api, tmp_path: Path) -> None:
    """The scenario "A member choice report": the report counts the member choices by source."""
    from horizon.evals import watch_suites

    await _agent(api)
    opts = Options("freerun", profile="agent", mode="debate", runs=2)
    s = watch_suites.FreeRun()
    res = await s.run(env_for(api, tmp_path, opts), s.plan(opts, api.rt.prices, paid=False))
    text = "\n".join(res.summary)
    assert text.startswith("## Free run (debate): 2 debate(s)")
    assert "### free-2v2: 12 arguments" in text and "### free-panel: 12 arguments" in text
    lines = [x for x in text.splitlines() if x.startswith("- member choices: ")]
    assert len(lines) == 2 and all("Jev " in x and "unsure " in x and "late " in x for x in lines)
    first = res.rows[0]
    assert sum(first["members"].values()) == 4                            # 2 v 2: a choice at each phase's first slot
    assert "(agent column)" in text and "host lines: " in text
    assert first["verdict"] and first["verdict"]["decidedBy"] == "arbiter"


# ── 9.10: smoke ──
async def test_smoke_in_ci_runs_a_debate_to_its_verdict(tmp_path: Path) -> None:
    """The scenario "Smoke in CI": in test mode a Quick 2 v 2 debate reaches its verdict with host lines and scores,
    plus one debate-plan timing request and one rubric request (the socket guard is on for every test)."""
    from horizon.evals.runner import Runner
    from tests.conftest import make_config

    said: list[str] = []
    r = Runner(make_config(tmp_path, test_mode=True))
    r.out = said.append  # type: ignore[method-assign]
    assert await r.run(Options("smoke", limit=5, yes=True)) == 0, said
    (run,) = [p for p in (tmp_path / "evals").iterdir() if p.is_dir()]
    report = (run / "naive" / "report.md").read_text(encoding="utf-8")
    assert "- debate: 8 argument(s), 3 host line(s), verdict arbiter with 8 score(s)" in report
    assert "- debate-plan timing: 1 request(s)" in report and "- rubric: 8 bar(s)" in report


# ── 10.11's builders, on a committed M10 history as the fixture ──
def test_the_fresh_cuts_and_the_growth_are_cut_with_the_live_state() -> None:
    sys.path.insert(0, str(DATASETS / "who_speaks"))
    fresh = load("who_fresh_build", DATASETS / "who_speaks" / "fresh.py")
    rows = fresh.build_fresh(fresh.profiles(), {("sunnyhollow", 1): ("takeshi", "en"), ("sunnyhollow", 4): ("rin", "en")})
    assert [r["id"] for r in rows] == ["wsf-001", "wsf-002"]
    assert all(r["fresh"] and r["split"] == "test" for r in rows)
    assert "last_spoke" not in json.dumps(rows[0]["item"]["state"])
    grow = load("emotion_watch_2_build", DATASETS / "emotion" / "build_watch_2.py")
    items = grow.build(grow.seed_profiles(), [("sunnyhollow", 0, ["happy"], False, "en"),
                                              ("sunnyhollow", 4, ["thinking"], True, "en")], tests=0)
    assert [r["question_id"] for r in items] == ["emotion_opening", "emotion_line"]
    assert items[1]["item"]["state"]["mode"] == "watch" and items[1]["item"]["name"]
