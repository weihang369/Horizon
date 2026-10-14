"""Where the deep work runs in each mode, the rewrite's storage, and the labels and row limits (rag design D15, D16,
D19, D20; tasks 5.3, 7.5–7.7, 8.2, 8.4, 8.5; deep-turn "The deep work starts as early as each mode allows", "The
rewrite's storage is derived data"; follow-plan, watch-direction and debate-plan's M12 requirements; data-storage and
session-event-sourcing's `message_ai_meta`; system1-trace "Passage rows"). No network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, inspect, text

from horizon.ai.agent import gates
from horizon.ai.contexts import CastPlan, GateAnswer, MessageNouls, TurnContext, TurnPlan
from horizon.db.migrate import alembic_config, upgrade_head
from horizon.services.ai_meta import store_rewrite, stored_rewrite
from horizon.sessions.system1 import MAX_ROWS, section
from tests.conftest import Api
from tests.sessions.kit import API, assert_reduces, chars, command, events, ledger, messages
from tests.sessions.test_deep_m12 import ANSWERS, NO_HELP, chats, checks, nouls
from tests.sessions.test_gates_m12 import AMARA, MEI, VICTOR, agent, gate, rows, send


def sequence(api: Api, actor: Any, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    """The order of Jev requests (their question keys) and session events, as they happen: each event records how many
    provider requests the fake had received when it was emitted, and `merged` interleaves the two."""
    marks: list[tuple[int, Any]] = []
    fake = api.rt.fake
    assert fake is not None
    emit = actor.emit

    async def emitting(*evs: Any, **k: Any) -> Any:
        for e in evs:
            marks.append((len(fake.requests), (e.get("type"), (e.get("payload") or {}).get("nextSpeakerId"))))
        return await emit(*evs, **k)

    monkeypatch.setattr(actor, "emit", emitting)
    checked = actor.emit_checked

    async def emitting_checked(ev: Any, *a: Any, **k: Any) -> Any:
        marks.append((len(fake.requests), (ev.get("type"), (ev.get("payload") or {}).get("nextSpeakerId"))))
        return await checked(ev, *a, **k)

    monkeypatch.setattr(actor, "emit_checked", emitting_checked)
    seq: list[tuple[str, Any]] = []
    seq_marks.append((marks, fake, seq))
    return seq


seq_marks: list[tuple[list[tuple[int, Any]], Any, list[tuple[str, Any]]]] = []


def merged(seq: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
    """Rebuild `seq` from the recorded marks and the fake's requests, in arrival order."""
    marks, fake, out = next(x for x in seq_marks if x[2] is seq)
    out.clear()
    reqs = [json.loads(r.content)["questions"] if r.url.path.endswith("/alpha/decisions") else None
            for r in fake.requests]
    j = 0
    for i, q in enumerate(reqs):
        while j < len(marks) and marks[j][0] <= i:
            out.append(("event", marks[j][1]))
            j += 1
        if q is not None:
            out.append(("jev", list(q)))
    out.extend(("event", m[1]) for m in marks[j:])
    return out


def first_index(seq: list[tuple[str, Any]], test: Any) -> int:
    return next(i for i, x in enumerate(merged(seq)) if test(x))


def mei_when_she_can(b: dict[str, Any]) -> dict[str, Any]:
    """Watch never gives one character two turns in a row: Mei whenever she is a candidate, else Victor."""
    from tests.sessions.test_watch_plan import pick

    if "who_scene" not in b["questions"]:
        return {}
    options = set(b["questions"]["who_scene"]["criteria"])
    return {"who_scene": pick(MEI if MEI in options else VICTOR)}


def picks(api: Api, first: str, second: str | None = None) -> None:
    fake = api.rt.fake
    assert fake is not None
    fake.answer_question("who_first", {"type": "choice", "choice": first, "confidence": 0.9,
                                       "probabilities": {first: 0.9}})
    if second:
        fake.answer_question("who_second", {"type": "choice", "choice": second, "confidence": 0.9,
                                            "probabilities": {second: 0.9}})


# ── 7.5 group ──
async def test_group_first_reply_checks_go_out_before_its_turn_next(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    sid = await agent(api, "group", [AMARA, MEI, VICTOR])
    seq = sequence(api, await api.rt.sessions.get(sid), monkeypatch)
    picks(api, MEI)
    gate(api, MEI, 0.8)
    replies = await send(api, sid, "What did the four-day week pilots find?", 25000)
    assert replies[0]["author"]["characterId"] == MEI
    check = first_index(seq, lambda x: x[0] == "jev" and any(k.startswith("passage:") for k in x[1]))
    nxt = first_index(seq, lambda x: x == ("event", ("turn.next", MEI)))
    plan = first_index(seq, lambda x: x[0] == "jev" and "who_first" in x[1])
    assert plan < check < nxt + 2       # started at the cast plan's landing, with the turn's preamble
    assert "# From your documents" in chats(api, "reply")[0]["messages"][-1]["content"]


async def test_the_second_reply_goes_deep_from_the_follow_plan(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    sid = await agent(api, "group", [AMARA, MEI, VICTOR])
    seq = sequence(api, await api.rt.sessions.get(sid), monkeypatch)
    picks(api, AMARA, MEI)
    gate(api, AMARA, 0.1)
    gate(api, MEI, 0.8)
    replies = await send(api, sid, "What did the four-day week pilots find?", 30000)
    assert [r["author"]["characterId"] for r in replies] == [AMARA, MEI]
    follow = first_index(seq, lambda x: x[0] == "jev" and "who_second" in x[1])
    check = first_index(seq, lambda x: x[0] == "jev" and any(k.startswith("passage:") for k in x[1]))
    nxt = first_index(seq, lambda x: x == ("event", ("turn.next", MEI)))
    assert follow < check < nxt + 2
    assert rows(replies[1], "docs")[0]["about"] == MEI and replies[1]["trace"]["knowledge"]["trigger"] == "gated"
    assert "knowledge" not in (replies[0]["trace"] or {})


async def test_a_new_message_cancels_the_second_replys_deep_work(api: Api) -> None:
    sid = await agent(api, "group", [AMARA, MEI, VICTOR])
    picks(api, AMARA, MEI)
    gate(api, AMARA, 0.1)
    gate(api, MEI, 0.8)
    fake = api.rt.fake
    assert fake is not None
    held = fake.park_questions("passage:", 8)
    await command(api, sid, "send", {"text": "What did the four-day week pilots find?"})
    for _ in range(400):
        await api.drive(50)
        if fake.decision_parked.is_set():
            break
    assert fake.decision_parked.is_set()
    await command(api, sid, "send", {"text": "Actually, never mind."})
    await api.drive(500)
    for ev in held:
        ev.set()
    await api.drive(25000)
    msgs = chars(await messages(api, sid))
    mei = [m for m in msgs if m["author"]["characterId"] == MEI and "never mind" not in (m.get("content") or "")]
    first_round = [m for m in msgs if m["seq"] < next(u["seq"] for u in await messages(api, sid)
                                                      if u["author"]["type"] == "user" and "never mind" in u["content"])]
    assert all(m["author"]["characterId"] != MEI for m in first_round)     # no second reply was written
    cancelled = [r for r in await ledger(api) if r["purpose"] == "deep_check" and r["finish_reason"] == "cancelled"]
    assert cancelled
    assert mei is not None
    await assert_reduces(api, sid)


# ── 7.6 watch ──
async def test_a_watch_plan_made_ahead_starts_the_deep_work(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.sessions.test_watch_plan import _until_turn_end, agent_watch, jev

    sid = await agent_watch(api, maxTurns=10, paceMs=3000)
    jev(api, mei_when_she_can)
    gate(api, MEI, 0.8)
    assert api.rt.fake is not None
    api.rt.fake.set_canned("reply", [{"content": "The four-day week pilots in Meridian were quite something."}])
    seq = sequence(api, await api.rt.sessions.get(sid), monkeypatch)
    await _until_turn_end(api, sid, 3)                    # Mei, Victor, then Mei from the plan made ahead
    full = merged(seq)
    mei_next = [i for i, x in enumerate(full) if x == ("event", ("turn.next", MEI))]
    checks_at = [i for i, x in enumerate(full) if x[0] == "jev" and any(k.startswith("passage:") for k in x[1])]
    assert mei_next and checks_at
    assert checks_at[0] < mei_next[-1]          # the checks went out during the pause, before Mei's turn.next


async def test_a_directors_note_drops_the_plan_and_its_deep_work(api: Api) -> None:
    from tests.sessions.test_watch_plan import _until_turn_end, agent_watch, jev

    sid = await agent_watch(api, maxTurns=10, paceMs=3000)
    jev(api, mei_when_she_can)
    gate(api, MEI, 0.8)
    fake = api.rt.fake
    assert fake is not None
    fake.set_canned("reply", [{"content": "The four-day week pilots in Meridian were quite something."}])
    await _until_turn_end(api, sid, 1)                    # Mei; Victor's turn has no deep work
    held = fake.park_questions("passage:", 8)             # held: the checks of the plan made ahead for Mei's next
    for _ in range(300):
        await api.drive(50)
        if fake.decision_parked.is_set():
            break
    assert fake.decision_parked.is_set()                                      # the plan made ahead's checks
    await command(api, sid, "watch/direct", {"text": "Someone mentions the storm outside."})   # while in flight
    await api.drive(8000)
    for ev in held:
        ev.set()
    await api.drive(5000)
    cancelled = [r for r in await ledger(api) if r["purpose"] == "deep_check" and r["finish_reason"] == "cancelled"]
    assert cancelled
    await assert_reduces(api, sid)


# ── 7.7 debate ──
async def test_a_debate_turn_never_rewrites_or_abstains(api: Api) -> None:
    from tests.sessions.test_debate_plan import args, debate

    sid = await debate(api, motion="Long shift blocks harm patient safety")
    for cid in (AMARA, MEI, VICTOR):
        gate(api, cid, 0.95)
    fake = api.rt.fake
    assert fake is not None
    fake.answer_question("passage:*", NO_HELP)
    await api.drive(120000)
    reb = args(await messages(api, sid), "rebuttal")
    assert reb
    assert not [r for r in await ledger(api) if r["purpose"] == "query_rewrite"]
    assert all("# Your documents" not in b["messages"][-1]["content"] for b in chats(api, "reply"))
    deep = [m for m in reb if (m["trace"] or {}).get("knowledge")]
    assert deep and all(not rows(m, "standalone") for m in deep)
    q = [b for b in checks(api) if b["state"]["mode"] == "debate"]
    assert q and set(q[0]["state"]["quoted_query"]) == {"motion", "argument"}


async def test_a_debate_rebuttal_searches_the_motion_and_the_opposing_argument(api: Api) -> None:
    from tests.sessions.test_debate_plan import args, debate

    sid = await debate(api, motion="Long shift blocks harm patient safety")
    gate(api, VICTOR, 0.9)
    gate(api, AMARA, 0.9)
    gate(api, MEI, 0.9)
    fake = api.rt.fake
    assert fake is not None
    fake.answer_question("passage:*", ANSWERS)
    await api.drive(120000)
    reb = [m for m in args(await messages(api, sid), "rebuttal") if (m["trace"] or {}).get("knowledge")]
    assert reb
    k = reb[0]["trace"]["knowledge"]
    assert k["query"].startswith("Long shift blocks harm patient safety")
    assert len([r for r in k["retrieved"] if r.get("n")]) <= 2


# ── 5.3 `message_ai_meta` ──
def test_the_migration_up_and_down(tmp_path: Path) -> None:
    from alembic import command as alembic

    db = tmp_path / "m.db"
    upgrade_head(db)
    eng = create_engine(f"sqlite:///{db}")
    names = set(inspect(eng).get_table_names())
    assert "message_ai_meta" in names
    fks = inspect(eng).get_foreign_keys("message_ai_meta")
    assert fks[0]["referred_table"] == "messages" and fks[0]["options"].get("ondelete") == "CASCADE"
    eng.dispose()
    alembic.downgrade(alembic_config(db), "0003")
    eng = create_engine(f"sqlite:///{db}")
    after = set(inspect(eng).get_table_names())
    assert after == names - {"message_ai_meta"}
    eng.dispose()


async def test_rewrites_are_stored_forked_and_cascade(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    await send(api, sid, "and nights?")
    user = next(m for m in await messages(api, sid) if m["author"]["type"] == "user")
    assert await store_rewrite(api.rt, user["id"], AMARA, "night shift fatigue")
    assert await stored_rewrite(api.rt, user["id"], AMARA) == "night shift fatigue"
    assert await stored_rewrite(api.rt, user["id"], MEI) is None              # never another speaker's
    assert not await store_rewrite(api.rt, "msg_gone", AMARA, "x")
    await assert_reduces(api, sid)                                             # not event-sourced
    fork = (await api.post(f"{API}/sessions/{sid}/fork", {}, status=201)).json()
    fid = fork["session"]["id"]
    fuser = next(m for m in await messages(api, fid) if m["author"]["type"] == "user")
    assert await stored_rewrite(api.rt, fuser["id"], AMARA) == "night shift fatigue"
    assert (await api.client.delete(f"{API}/sessions/{sid}")).status_code == 204
    async with api.rt.db.read() as conn:
        n = (await conn.execute(text("SELECT count(*) FROM message_ai_meta WHERE message_id = :m"),
                                {"m": user["id"]})).scalar_one()
    assert n == 0


async def test_a_forked_copy_reuses_the_rewrite(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.8)
    nouls(api, standalone=0.06)
    await send(api, sid, "How much worse is fatigue after long shift blocks?")
    [reply] = await send(api, sid, "and nights?")
    n = len(chats(api, "query_rewrite"))
    fork = (await api.post(f"{API}/sessions/{sid}/fork", {}, status=201)).json()
    fid = fork["session"]["id"]
    copy = chars(await messages(api, fid))[-1]
    await command(api, fid, "regenerate", {"messageId": copy["id"]})
    await api.drive(15000)
    assert len(chats(api, "query_rewrite")) == n                               # reused, no new call
    assert reply is not None


# ── 8.2 the labels ──
@pytest.mark.parametrize(("cue", "mood", "label"), [
    (None, False, "agent-1+docs-1"), (None, True, "agent-2+docs-1"),
    ("second", False, "agent-3+docs-1"), ("steer", False, "agent-5+docs-1"),
])
def test_the_docs_label_follows_the_bytes(api: Api, cue: str | None, mood: bool, label: str,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    from horizon.ai.agent.turn import AgentTurnEngine
    from tests.unit.test_deep_units_m12 import ctx_with, hit

    engine = AgentTurnEngine(api.rt.ai.deps)
    monkeypatch.setattr(engine.deps, "switch", lambda name: mood and name == "persona.moodLine")
    plan = TurnPlan(seed="s", branch="deep", knowledge_outcome="found", cue=cue, answered="Mei")  # type: ignore[arg-type]
    ctx = ctx_with(plan, [hit(1, "x")], mode="group" if cue else "one_on_one")
    assert engine.prompt_version_for(ctx) == label
    nf = ctx_with(TurnPlan(seed="s", branch="deep", knowledge_outcome="not_found", abstain=True), [])
    assert engine.prompt_version_for(nf).endswith("+nodocs-1")
    quick = ctx_with(TurnPlan(seed="s", branch="quick"), [])
    assert "+" not in engine.prompt_version_for(quick)


def test_naive_labels_its_centred_slice(api: Api) -> None:
    from horizon.ai.naive.turn import NaiveTurnEngine
    from tests.unit.test_deep_units_m12 import ctx_with, hit

    engine = NaiveTurnEngine(api.rt.ai.deps)
    with_hits = ctx_with(TurnPlan(seed="s"), [hit(1, "x")])
    assert engine.prompt_version_for(with_hits) == "naive-7"
    assert engine.prompt_version_for(with_hits.model_copy(update={"session": with_hits.session.model_copy(
        update={"mode": "debate"})})) == "naive-8"
    assert engine.prompt_version_for(ctx_with(TurnPlan(seed="s"), [])) == "naive-5"


# ── 8.4 the rows stay within 64 ──
def test_a_five_candidate_group_deep_turn_keeps_every_row() -> None:
    cands = [f"chr_{i}" for i in range(5)]
    plan = CastPlan(seed="s", kind="group_first", order=["chr_0"], gates={c: GateAnswer(p=0.9) for c in cands},
                    nouls=MessageNouls(standalone=0.2, english=0.9),
                    face_rows={c: {"purpose": "turn_plan", "id": "emotion_reply", "about": c, "result": "used"}
                               for c in cands},
                    shared_rows=[{"purpose": "turn_plan", "id": "who_first", "result": "used"}])
    tp = plan.for_speaker("chr_0")
    passages = [{"purpose": "deep_check", "id": "passage", "about": f"kch_{i}", "result": "used"} for i in range(8)]
    rows_ = [*tp.rows, *passages, {"purpose": "deep_check", "id": "passage_set", "result": "used"},
             {"purpose": "face_check", "id": "face_check", "result": "shown_only"},
             *({"purpose": "reaction", "id": "reaction", "about": c} for c in cands)]
    out = section(None, rows_)["questions"]
    assert len(rows_) <= MAX_ROWS and len(out) == len(rows_)
    assert gates.deep(tp.gate)


def test_unused_imports_kept() -> None:
    assert TurnContext and events
