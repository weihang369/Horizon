"""The memory writer (memory design D12–D19; long-term-memory "One call rewrites every present character's list",
"Jev scores importance and guards rewrites", "A near-duplicate reinforces"; ai-ports "The memory writer port reads a
stretch"; embedding-spaces "Memory work embeds each new text once")."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from horizon.ai.decider import NoulAnswer, Score, ScoreAnswer
from horizon.ai.memory import jev
from horizon.ai.memory import rewrite as mem1
from horizon.ai.memory.writers import AgentMemoryWriter, NaiveMemoryWriter
from horizon.ai.ports import Insert, Reinforce, Supersede
from horizon.ai.profile import ProfileSpec
from horizon.ai.questions import bank, check_lock
from horizon.ai.scripted.ports import NoMemoryWriter
from horizon.gateway.fake import load_canned
from horizon.services.memory.block import ListedMemory
from horizon.services.memory.runs import RunContext
from horizon.services.memory.stretch import Present, Stretch, StretchLine
from tests.conftest import Api
from tests.helpers.storm import after_storm, park_next_chat, storm
from tests.sessions.kit import API, command, create, ledger

AMARA, MEI, MERIDIAN = "chr_seedAmara", "chr_seedMei", "wld_seedMeridian"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "memory" / "memory-2.prompt.txt"


# ── builders ──
def _present(n: int, cid: str, name: str, memories: list[ListedMemory] | None = None) -> Present:
    return Present(n=n, character_id=cid, name=name, role="nurse" if n == 1 else "chef", memories=memories or [],
                   about=f"{name} is calm. {name} likes tea.")


def _mem(i: int, text_: str, importance: float = 0.5, mid: str | None = None, kind: str = "fact") -> ListedMemory:
    return ListedMemory(label=f"m{i}", id=mid or f"mem_{i}", kind=kind, text=text_, importance=importance)


def _stretch(present: list[Present] | None = None, *, session_id: str = "ses_x", lines: int = 3) -> Stretch:
    present = present if present is not None else [
        _present(1, AMARA, "Amara", [_mem(1, "Kai studies law."), _mem(2, "Kai quit coffee.", 0.6)]),
        _present(2, MEI, "Mei", [_mem(1, "Kai's sister Mia is a nurse in Ipoh.", 0.7, "mem_mei1")])]
    ls = [StretchLine(n=i, message_id=f"msg_{i}", variant_id=f"msg_{i}_v1", seq=10 + i,
                      speaker="Kai" if i % 2 else "Amara", text=f"line {i} about exams and sleep",
                      author="user" if i % 2 else "character", character_id=None if i % 2 else AMARA)
          for i in range(1, lines + 1)]
    return Stretch(session_id=session_id, world_id=MERIDIAN, world_name="Meridian", user_name="Kai", mode="group",
                   header="", context=["Kai: hello", "Amara: hi Kai"], lines=ls, present=present, from_seq=10,
                   upto_seq=10 + lines, reread_ids=[])


def _answer(*changes: dict[str, Any]) -> str:
    return json.dumps({"changes": list(changes)})


class FakeIO:
    """The run's reads, in memory: current memories, the one embedding, and a set nearest neighbour."""

    def __init__(self, current: dict[str, list[tuple[str, str, float]]] | None = None,
                 near: tuple[str, float, float] | None = None, embeds: bool = True) -> None:
        self._current = current or {}
        self.near = near
        self.embeds = embeds
        self.embedded: list[list[str]] = []

    async def current(self, character_id: str) -> list[tuple[str, str, float]]:
        return list(self._current.get(character_id, []))

    async def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None:
        self.embedded.append(list(texts))
        return ("space_a", [[1.0, 0.0] for _ in texts]) if self.embeds else None

    async def nearest(self, character_id: str, space_id: str, vector: list[float]) -> tuple[str, float, float] | None:
        return self.near


async def _ctx(api: Api, io: Any = None) -> RunContext:
    sid = (await create(api, "group", [AMARA, MEI]))["session"]["id"]
    return RunContext(world_id=MERIDIAN, session_id=sid, now=api.rt.clock.now,
                      knobs=api.rt.runtime_cfg.runtime.memory, io=io or FakeIO())


def _agent(api: Api, profile: str = "agent") -> Any:
    api.rt.set_profile(ProfileSpec(profile=profile, test_mode=True))  # type: ignore[arg-type]
    return api.rt.ai.memory_writer(True)


def _canned(api: Api, *contents: str, finish: str = "stop") -> None:
    assert api.rt.fake is not None
    api.rt.fake.set_canned("memory", [{"content": c, "finish_reason": finish} for c in contents])


async def _purposes(api: Api) -> list[str]:
    return [str(r["purpose"]) for r in await ledger(api)]


# ── 3.1 the port ──
@pytest.mark.parametrize(("profile", "key", "test_mode", "want"), [
    ("scripted", True, True, NoMemoryWriter), ("naive", True, True, NaiveMemoryWriter),
    ("agent", True, True, AgentMemoryWriter), ("agent", False, True, NoMemoryWriter),
    ("naive", False, False, NaiveMemoryWriter), (None, True, True, AgentMemoryWriter),
    (None, True, False, NaiveMemoryWriter), (None, False, True, NoMemoryWriter)])
async def test_the_memory_writer_port_resolves_per_profile(api: Api, profile: Any, key: bool, test_mode: bool,
                                                           want: type) -> None:
    api.rt.set_profile(ProfileSpec(profile=profile, test_mode=test_mode))
    assert isinstance(api.rt.ai.memory_writer(key), want)


# ── 3.2 memory-1 ──
def test_the_prompt_bytes_match_the_committed_fixture() -> None:
    present = [_present(1, AMARA, "Amara", [_mem(1, "Kai studies law.")]), _present(2, MEI, "Mei")]
    s = _stretch(present)
    got = mem1.SYSTEM + "\n\n=== user ===\n" + mem1.user_message(s) + "\n"
    assert FIXTURE.read_text(encoding="utf-8") == got


def test_max_tokens_grow_with_the_cast_and_stop_at_3000() -> None:
    assert mem1.max_tokens(1) == 500 and mem1.max_tokens(2) == 800 and mem1.max_tokens(20) == 3000


def test_the_code_checks_drop_what_is_invalid() -> None:
    s = _stretch()
    long_text = " ".join(f"w{i}" for i in range(45))
    out = mem1.check([
        {"for": 3, "op": "add", "kind": "fact", "text": "x", "source": 1},              # unknown character
        {"for": "one", "op": "add", "kind": "fact", "text": "x", "source": 1},          # bad for
        {"for": 1, "op": "rewrite", "target": "m9", "kind": "fact", "text": "x", "source": 1},   # unknown target
        {"for": 1, "op": "add", "kind": "feeling", "text": "x", "source": 1},           # bad kind
        {"for": 1, "op": "add", "kind": "fact", "about": 7, "text": "x", "source": 1},  # bad about
        {"for": 1, "op": "add", "kind": "fact", "text": "x", "source": 99},             # unknown source line
        {"for": 1, "op": "add", "kind": "fact", "text": "  ", "source": 1},             # empty
        {"for": 1, "op": "delete", "target": "m1", "source": 1},                        # bad op
        {"for": 1, "op": "add", "kind": "event", "about": "user", "text": long_text, "source": 2, "weight": 4},
    ], s)
    assert len(out.changes) == 1 and len(out.log) == 8
    c = out.changes[0]
    assert c.text.split()[:40] == long_text.split()[:40] and c.text.split()[40:] == ["…"]
    assert c.line.message_id == "msg_2" and c.about_character_id is None and c.weight == 4


def test_seven_changes_for_one_character_keep_the_five_heaviest_and_every_confirm() -> None:
    s = _stretch()
    adds = [{"for": 1, "op": "add", "kind": "fact", "text": f"fact {i}", "source": 1, "weight": w}
            for i, w in enumerate([3, 1, 5, 4, 2, 5, 1])]
    out = mem1.check([*adds, {"for": 1, "op": "confirm", "target": "m1", "source": 2}], s)
    kept = sorted(c.weight or 0 for c in out.changes if c.op == "add")
    assert kept == [2, 3, 4, 5, 5] and any(c.op == "confirm" for c in out.changes)
    assert sum(1 for x in out.log if x["why"] == "over 5 changes") == 2


def test_exact_duplicates_in_one_answer_merge() -> None:
    s = _stretch()
    out = mem1.check([{"for": 1, "op": "add", "kind": "fact", "text": "Kai Likes Tea", "source": 1, "weight": 2},
                      {"for": 1, "op": "add", "kind": "fact", "text": "kai likes tea", "source": 3, "weight": 4}], s)
    assert [(c.text, c.weight) for c in out.changes] == [("kai likes tea", 4)]


def test_an_about_number_maps_to_that_character_and_drafts_carry_their_sources() -> None:
    s = _stretch()
    out = mem1.check([{"for": 1, "op": "add", "kind": "fact", "about": 2, "text": "Mei cooks well.", "source": 2}], s)
    c = out.changes[0]
    assert c.about_character_id == MEI and c.line.variant_id == "msg_2_v1"


async def test_a_parse_failure_retries_once_then_fails(api: Api) -> None:
    await api.set_key()
    _agent(api, "naive")
    _canned(api, "not json", _answer({"for": 1, "op": "add", "kind": "fact", "text": "Kai sleeps late.", "source": 1}))
    ctx = await _ctx(api)
    out = await mem1.call(api.rt.ai.deps, _stretch(), ctx)
    assert not out.failed and out.calls == 2 and [c.text for c in out.changes] == ["Kai sleeps late."]
    _canned(api, "not json")
    out = await mem1.call(api.rt.ai.deps, _stretch(), ctx)
    assert out.failed and out.calls == 2


async def test_a_length_answer_splits_the_characters_in_halves(api: Api) -> None:
    await api.set_key()
    _agent(api, "naive")
    seen: list[str] = []
    assert api.rt.fake is not None
    fake = api.rt.fake
    real = fake._canned

    def canned(purpose: str, body: dict[str, Any]) -> Any:
        seen.append(str(body["messages"][1]["content"]))
        if len(seen) == 1:
            fake.canned[purpose] = [{"content": '{"changes": [', "finish_reason": "length"}]
        else:
            fake.canned[purpose] = [{"content": _answer()}]
        return real(purpose, body)

    fake._canned = canned  # type: ignore[method-assign]
    _canned(api, "unused")
    out = await mem1.call(api.rt.ai.deps, _stretch(), await _ctx(api))
    assert not out.failed and len(seen) == 3
    assert "Write changes only for: 1. Amara" in seen[1] + seen[2] and "Write changes only for: 2. Mei" in seen[1] + seen[2]
    assert all("1. Amara (nurse)" in m and "2. Mei (chef)" in m for m in seen)   # everyone stays listed


# ── 3.3 the bank entries ──
def test_the_new_bank_entries_load_and_are_locked() -> None:
    b = bank()
    assert b.get("importance").purpose == "importance" and b.get("memory_guard").thresholds["t_keep"] == 0.35   # v3
    assert not [p for p in check_lock() if p.startswith(("importance", "memory_guard"))]
    q = b.question("importance", name="Amara", n=2)
    assert isinstance(q, Score) and len(q.levels) == 5 and "line 2" in q.instructions and "Amara" in q.instructions


def test_level_four_reads_as_three_quarters() -> None:
    assert ScoreAnswer(score=3).unit(5) == 0.75


def test_the_pricing_rows_hold_the_background_deadlines(api: Api) -> None:
    t = api.rt.decider.timeouts
    assert t.for_decision("importance") == 30.0 and t.for_decision("memory_guard") == 30.0


# ── 3.4 importance ──
async def test_importance_reads_jev_and_falls_back_to_the_hint(api: Api) -> None:
    await api.set_key()
    _agent(api)
    ctx = await _ctx(api)
    fx = api.rt.decider.fixtures
    fx.set("importance", "importance:l1", ScoreAnswer(score=3))
    p = _present(1, AMARA, "Amara")
    got = await jev.importance(api.rt.ai.deps, asyncio.Semaphore(10), ctx, p, "Kai", [("a", 2)])
    assert got == [jev.Scored(0.75, "fixture")]
    fx.clear()
    assert jev.hint(2) == 0.25 and jev.hint(None) == 0.5 and jev.hint(5) == 1.0


async def test_importance_late_takes_the_hint(api: Api) -> None:
    await api.set_key()
    _agent(api)
    ctx = await _ctx(api)
    assert api.rt.fake is not None
    ev = api.rt.fake.park_decision(api.rt.fake.counts["decisions"] + 1)
    task = asyncio.ensure_future(jev.importance(api.rt.ai.deps, asyncio.Semaphore(10), ctx,
                                                _present(1, AMARA, "Amara"), "Kai", [("a", 4), ("b", None)]))
    await api.drive(31_000)
    got = await task
    ev.set()
    await api.drive(10)
    assert got == [jev.Scored(0.75, "fallback"), jev.Scored(0.5, "fallback")]


def test_an_extra_question_rides_beside_importance_which_keeps_its_version() -> None:
    extra = {"instruction:l1": bank().question("importance", name="Amara", n=1)}   # M14's seam (D38)
    state, qs = jev.importance_request(_present(1, AMARA, "Amara"), "Kai", ["one line"], extra_questions=extra)
    assert set(qs) == {"importance:l1", "instruction:l1"}
    meta = qs["importance:l1"].meta
    assert meta is not None and meta.version == 1 and state["quoted_lines"] == {"l1": "one line"}
    assert state["quoted_about"] == "Amara is calm."


async def test_the_agent_rules_min_importance_higher_of_and_confirm(api: Api) -> None:
    await api.set_key()
    writer = _agent(api)
    fx = api.rt.decider.fixtures
    fx.set("importance", "importance:l1", ScoreAnswer(score=0))   # the add: 0.0 < minImportance → dropped
    fx.set("importance", "importance:l2", ScoreAnswer(score=1))   # the rewrite: max(0.6, 0.25) = 0.6
    fx.set("memory_guard", "memory_guard", NoulAnswer(p=0.9))
    _canned(api, _answer({"for": 1, "op": "add", "kind": "fact", "text": "Kai hums.", "source": 1, "weight": 5},
                         {"for": 1, "op": "rewrite", "target": "m2", "kind": "fact", "source": 1,
                          "text": "Kai quit coffee last month.", "weight": 2},
                         {"for": 1, "op": "confirm", "target": "m1", "source": 3}))
    res = await writer.on_stretch(_stretch(), await _ctx(api))
    ops = res.ops[AMARA]
    assert [type(o) for o in ops] == [Supersede, Reinforce]
    sup = ops[0]
    assert isinstance(sup, Supersede) and sup.old_ids == ["mem_2"] and sup.draft.importance == 0.6
    assert ops[1] == Reinforce("mem_1", 0.55)
    assert any(x["why"] == "below minImportance" for x in res.log)


# ── 3.5 the guard ──
@pytest.mark.parametrize(("p", "want"), [(0.9, Supersede), (0.2, Insert)])
async def test_the_guard_supersedes_at_t_keep_else_keeps_both(api: Api, p: float, want: type) -> None:
    await api.set_key()
    writer = _agent(api)
    api.rt.decider.fixtures.set("memory_guard", "memory_guard", NoulAnswer(p=p))
    _canned(api, _answer({"for": 2, "op": "rewrite", "target": "m1", "kind": "fact", "source": 1,
                          "text": "Kai's sister is a nurse."}))
    res = await writer.on_stretch(_stretch(), await _ctx(api))
    assert [type(o) for o in res.ops[MEI]] == [want]


async def test_a_late_guard_keeps_both(api: Api) -> None:
    await api.set_key()
    writer = _agent(api)
    api.rt.decider.fixtures.set("importance", "importance:l1", ScoreAnswer(score=2))
    _canned(api, _answer({"for": 2, "op": "rewrite", "target": "m1", "kind": "fact", "source": 1,
                          "text": "Kai's sister is a nurse."}))
    assert api.rt.fake is not None
    ev = api.rt.fake.park_decision(api.rt.fake.counts["decisions"] + 1)   # the guard (importance is a fixture)
    task = asyncio.ensure_future(writer.on_stretch(_stretch(), await _ctx(api)))
    await api.drive(31_000)
    res = await task
    ev.set()
    await api.drive(10)
    assert [type(o) for o in res.ops[MEI]] == [Insert]
    assert any(x["step"] == "guard" and "failed or late" in x["why"] for x in res.log)


async def test_a_rate_limited_guard_is_retried_once(api: Api) -> None:
    await api.set_key()
    writer = _agent(api)
    api.rt.decider.fixtures.set("importance", "importance:l1", ScoreAnswer(score=2))
    assert api.rt.fake is not None
    api.rt.fake.refuse_question("memory_guard")
    api.rt.fake.answer_question("memory_guard", {"type": "noul", "noul": 0.95})
    _canned(api, _answer({"for": 2, "op": "rewrite", "target": "m1", "kind": "fact", "source": 1,
                          "text": "Kai's sister Mia is a nurse in Ipoh, on nights."}))
    before = api.rt.fake.counts["decisions"]
    task = asyncio.ensure_future(writer.on_stretch(_stretch(), await _ctx(api)))
    await api.drive(2_000)
    res = await task
    assert api.rt.fake.counts["decisions"] - before == 2 and [type(o) for o in res.ops[MEI]] == [Supersede]


# ── 3.6 the duplicate check ──
async def test_a_near_duplicate_reinforces(api: Api) -> None:
    """Phase 10 (the user's choice): near (cosine ≥ dupCosine) asks Jev "same fact?"; yes reinforces."""
    await api.set_key()
    writer = _agent(api)
    assert api.rt.fake is not None
    api.rt.fake.answer_question("same_fact", {"type": "noul", "noul": 0.9})
    io = FakeIO(current={AMARA: [("mem_near", "Kai studies law.", 0.4)]}, near=("mem_near", 0.95, 0.4))
    _canned(api, _answer({"for": 1, "op": "add", "kind": "fact", "text": "Kai is studying law.", "source": 1}))
    before = api.rt.fake.counts["decisions"]
    res = await writer.on_stretch(_stretch(), await _ctx(api, io))
    assert res.ops[AMARA] == [Reinforce("mem_near", 0.45)] and res.vectors == {}
    assert api.rt.fake.counts["decisions"] - before == 2   # importance, then same fact?
    assert "memory_guard" in await _purposes(api)


async def test_a_near_line_with_a_new_detail_is_written(api: Api) -> None:
    """Cosine can't tell an extension from a rewording (m13.md): Jev says "different", so the add is written."""
    await api.set_key()
    writer = _agent(api)
    assert api.rt.fake is not None
    api.rt.fake.answer_question("same_fact", {"type": "noul", "noul": 0.1})
    io = FakeIO(current={AMARA: [("mem_near", "Kai studies law.", 0.4)]}, near=("mem_near", 0.98, 0.4))
    _canned(api, _answer({"for": 1, "op": "add", "kind": "fact", "text": "Kai studies law at UM, in his final year.",
                          "source": 1}))
    res = await writer.on_stretch(_stretch(), await _ctx(api, io))
    assert [type(o) for o in res.ops[AMARA]] == [Insert]
    log = [x for x in res.log if x["step"] == "duplicate"]
    assert log and log[0]["why"] == "near, but not the same fact: written" and log[0]["p"] == 0.1


async def test_a_far_add_asks_no_same_fact_question(api: Api) -> None:
    await api.set_key()
    writer = _agent(api)
    assert api.rt.fake is not None
    io = FakeIO(near=("mem_far", 0.84, 0.4))   # below the 0.85 pre-filter
    _canned(api, _answer({"for": 1, "op": "add", "kind": "fact", "text": "Kai plays the cello.", "source": 1}))
    before = api.rt.fake.counts["decisions"]
    res = await writer.on_stretch(_stretch(), await _ctx(api, io))
    assert [type(o) for o in res.ops[AMARA]] == [Insert] and api.rt.fake.counts["decisions"] - before == 1


async def test_a_case_folded_duplicate_reinforces_without_an_embedding(api: Api) -> None:
    await api.set_key()
    writer = _agent(api)
    io = FakeIO(current={AMARA: [("mem_c", "Kai Studies Law.", 0.5)]})
    _canned(api, _answer({"for": 1, "op": "add", "kind": "fact", "text": "kai studies law.", "source": 1}))
    res = await writer.on_stretch(_stretch(), await _ctx(api, io))
    assert res.ops[AMARA] == [Reinforce("mem_c", 0.55)] and io.embedded == []


async def test_a_new_add_rides_with_its_vector(api: Api) -> None:
    await api.set_key()
    writer = _agent(api)
    io = FakeIO(near=("mem_far", 0.3, 0.4))
    _canned(api, _answer({"for": 1, "op": "add", "kind": "fact", "text": "Kai plays the cello.", "source": 1}))
    res = await writer.on_stretch(_stretch(), await _ctx(api, io))
    assert [type(o) for o in res.ops[AMARA]] == [Insert] and res.vectors == {"Kai plays the cello.": {"space_a": [1.0, 0.0]}}
    assert io.embedded == [["Kai plays the cello."]]


async def _record_embeds(api: Api) -> list[list[str]]:
    assert api.rt.fake is not None
    fake = api.rt.fake
    seen: list[list[str]] = []
    real = fake._embed

    def spy(body: dict[str, Any]) -> Any:
        seen.append(list(body.get("input") or []))
        return real(body)

    fake._embed = spy  # type: ignore[method-assign]
    return seen


async def test_a_run_embeds_each_new_text_exactly_once(api: Api) -> None:
    await api.set_key()
    _agent(api)
    _canned(api, _answer({"for": 1, "op": "add", "kind": "about_user", "about": "user", "source": 1,
                          "text": "Kai plays the cello on Sundays."}))
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    await command(api, sid, "send", {"text": "I play the cello every Sunday."})
    await api.drive(15_000)
    seen = await _record_embeds(api)
    api.rt.memory_runs.request(sid)
    await api.rt.memory_runs.drain()
    carrying = [x for x in seen if any("Kai plays the cello on Sundays." in s for s in x)]
    assert len(carrying) == 1
    async with api.rt.db.read() as conn:
        n = (await conn.execute(text("SELECT count(*) FROM memory_items WHERE text = :x"),
                                {"x": "Kai plays the cello on Sundays."})).scalar_one()
    assert n == 1


# ── 3.7 the graph ──
async def test_the_graph_runs_a_two_character_stretch(api: Api) -> None:
    await api.set_key()
    writer = _agent(api)
    api.rt.decider.fixtures.set("memory_guard", "memory_guard", NoulAnswer(p=0.9))
    assert api.rt.fake is not None
    _purpose, canned = load_canned("memory-writes")
    api.rt.fake.set_canned("memory", canned)
    s = _stretch()
    res = await writer.on_stretch(s, await _ctx(api, FakeIO(near=None)))
    assert [type(o) for o in res.ops[AMARA]] == [Insert, Reinforce]
    assert [type(o) for o in res.ops[MEI]] == [Supersede]
    out = await writer.graph.ainvoke({"stretch": s, "ctx": await _ctx(api, FakeIO()), "path": []})
    assert out["path"] == ["rewrite", "judge", "ops"]


async def test_cancelling_mid_graph_cancels_its_jev_reads(api: Api) -> None:
    await api.set_key()
    writer = _agent(api)
    _canned(api, _answer({"for": 1, "op": "add", "kind": "fact", "text": "Kai hums.", "source": 1}))
    assert api.rt.fake is not None
    api.rt.fake.decision_parked.clear()
    ev = api.rt.fake.park_decision(api.rt.fake.counts["decisions"] + 1)
    ctx = await _ctx(api)
    task = asyncio.ensure_future(writer.on_stretch(_stretch(), ctx))
    await asyncio.wait_for(api.rt.fake.decision_parked.wait(), 5)
    await storm(task)
    assert task.cancelled()
    ev.set()
    await api.drive(10)
    await after_storm(api, ctx.session_id)


# ── 3.8 naive ──
async def test_a_naive_run_makes_one_memory_call_and_no_jev_request(api: Api) -> None:
    await api.set_key()
    _agent(api, "naive")
    _canned(api, _answer({"for": 1, "op": "add", "kind": "about_user", "about": "user", "source": 1,
                          "text": "Kai is nervous about his finals.", "weight": 4},
                         {"for": 1, "op": "add", "kind": "fact", "source": 1, "text": "Amara met Kai today."}))
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    await command(api, sid, "send", {"text": "My finals are next week and I'm nervous."})
    await api.drive(15_000)
    before = await _purposes(api)
    api.rt.memory_runs.request(sid)
    await api.rt.memory_runs.drain()
    new = (await _purposes(api))[len(before):]
    assert new.count("memory") == 1 and not {"importance", "memory_guard"} & set(new)
    async with api.rt.db.read() as conn:
        rows = (await conn.execute(text("SELECT text, importance, source_mode FROM memory_items WHERE character_id = :c "
                                        "AND is_seed = 0"), {"c": AMARA})).all()
    assert sorted((r[0], r[1], r[2]) for r in rows) == [("Amara met Kai today.", 0.5, "one_on_one"),
                                                         ("Kai is nervous about his finals.", 0.75, "one_on_one")]


async def test_naive_skips_an_exact_duplicate_and_supersedes_a_rewrite(api: Api) -> None:
    await api.set_key()
    writer = _agent(api, "naive")
    io = FakeIO(current={AMARA: [("mem_1", "Kai studies law.", 0.5)]})
    _canned(api, _answer({"for": 1, "op": "add", "kind": "fact", "text": "KAI STUDIES LAW.", "source": 1},
                         {"for": 1, "op": "rewrite", "target": "m2", "kind": "fact", "source": 1,
                          "text": "Kai quit coffee in May.", "weight": 1}))
    res = await writer.on_stretch(_stretch(), await _ctx(api, io))
    ops = res.ops[AMARA]
    assert len(ops) == 1 and isinstance(ops[0], Supersede) and ops[0].draft.importance == 0.6


# ── 3.9 end to end, on canned answers ──
async def test_a_paused_one_on_one_writes_the_canned_memories_and_the_list_shows_them(api: Api) -> None:
    await api.set_key()
    api.rt.set_profile(ProfileSpec(test_mode=True))   # test mode with a key: the `agent` writer (D18)
    assert (await api.post(f"{API}/_test/canned", {"purpose": "memory", "set": "memory-writes"})).status_code == 204
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    await command(api, sid, "send", {"text": "Exams again. I barely sleep and I'm off coffee."})
    await api.drive(15_000)
    assert (await api.post(f"{API}/sessions/{sid}/leave", {})).status_code in (200, 202, 204)
    await api.drive(2000)
    await api.rt.memory_runs.drain()
    items = (await api.json(f"{API}/characters/{AMARA}/memory"))
    items = items.get("items", items) if isinstance(items, dict) else items
    texts = [i["text"] for i in items]
    assert "Kai sleeps badly before exams and is trying to cut back on coffee." in texts
    assert any(e["outcome"] == "committed" and e["sessionId"] == sid for e in api.rt.memory_runs.log)


# ── 3.10 the writer storms ──
async def test_a_run_cut_during_the_rewrite_call_writes_nothing(api: Api) -> None:
    await api.set_key()
    api.rt.set_profile(ProfileSpec(profile="agent", test_mode=True))
    assert (await api.post(f"{API}/_test/canned", {"purpose": "memory", "set": "memory-writes"})).status_code == 204
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    await command(api, sid, "send", {"text": "Exams again."})
    await api.drive(15_000)
    assert api.rt.fake is not None
    api.rt.fake.chat_parked.clear()
    ev = park_next_chat(api.rt, "memory")
    api.rt.memory_runs.request(sid)
    await asyncio.wait_for(api.rt.fake.chat_parked.wait(), 5)
    run = api.rt.memory_runs._running[sid].task
    await storm(run)
    ev.set()
    await api.drive(10)
    await after_storm(api, sid)
    async with api.rt.db.read() as conn:
        seq = (await conn.execute(text("SELECT memory_seq FROM sessions WHERE id = :s"), {"s": sid})).scalar_one()
        n = (await conn.execute(text("SELECT count(*) FROM memory_items WHERE character_id = :c AND is_seed = 0"),
                                {"c": AMARA})).scalar_one()
    assert seq == 0 and n == 0


async def test_a_run_cut_during_its_jev_requests_writes_nothing(api: Api) -> None:
    await api.set_key()
    api.rt.set_profile(ProfileSpec(profile="agent", test_mode=True))
    assert (await api.post(f"{API}/_test/canned", {"purpose": "memory", "set": "memory-writes"})).status_code == 204
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    await command(api, sid, "send", {"text": "Exams again."})
    await api.drive(15_000)
    assert api.rt.fake is not None
    api.rt.fake.decision_parked.clear()
    ev = api.rt.fake.park_decision(api.rt.fake.counts["decisions"] + 1)
    api.rt.memory_runs.request(sid)
    await asyncio.wait_for(api.rt.fake.decision_parked.wait(), 5)
    await storm(api.rt.memory_runs._running[sid].task)
    ev.set()
    await api.drive(10)
    await after_storm(api, sid)
    async with api.rt.db.read() as conn:
        seq = (await conn.execute(text("SELECT memory_seq FROM sessions WHERE id = :s"), {"s": sid})).scalar_one()
    assert seq == 0


async def test_a_run_cut_during_its_embedding_writes_nothing(api: Api) -> None:
    await api.set_key()
    api.rt.set_profile(ProfileSpec(profile="agent", test_mode=True))
    assert (await api.post(f"{API}/_test/canned", {"purpose": "memory", "set": "memory-writes"})).status_code == 204
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    await command(api, sid, "send", {"text": "Exams again."})
    await api.drive(15_000)
    assert api.rt.fake is not None
    api.rt.fake.embed_parked.clear()
    ev = api.rt.fake.park_embedding(api.rt.fake.counts["embeddings"] + 1)
    api.rt.memory_runs.request(sid)
    await asyncio.wait_for(api.rt.fake.embed_parked.wait(), 5)
    await storm(api.rt.memory_runs._running[sid].task)
    ev.set()
    await api.drive(10)
    await after_storm(api, sid)
    async with api.rt.db.read() as conn:
        seq = (await conn.execute(text("SELECT memory_seq FROM sessions WHERE id = :s"), {"s": sid})).scalar_one()
    assert seq == 0
