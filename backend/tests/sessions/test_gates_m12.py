"""The retrieval gates in every plan (rag design D6–D8, D20; tasks 4.1–4.5; turn-plan "Jev call 1 is one request with
only the questions that apply", "Only the speaker's gate is used"; follow-plan "The follow plan asks the gates";
debate-plan "The debate plan asks 'needs documents?' per member"; deep-turn "A turn goes deep only on its gate").
No network: the fake answers every gate no unless a test sets it."""

from __future__ import annotations

import json
from typing import Any

from horizon.ai.agent import gates
from horizon.ai.agent.plan_state import LIMIT, Candidate, PlanStateInput, build_turn_plan_state
from horizon.ai.contexts import CastPlan, GateAnswer, MessageNouls
from horizon.domain.timeutil import ms_from_iso
from horizon.sessions.context import document_titles
from tests.conftest import Api
from tests.sessions.kit import API, chars, command, create, events, messages

AMARA, MEI, VICTOR = "chr_seedAmara", "chr_seedMei", "chr_seedVictor"
HANA, RIN, TAKESHI = "chr_seedHana", "chr_seedRin", "chr_seedTakeshi"

SAFETY_KEYS = frozenset({"unsafe_request", "unsafe_note", "at_risk"})   # M14: the safety questions ride every plan


def unsafe_free(keys: Any) -> list[str]:
    """A request's question keys without M14's safety questions (their own tests pin those)."""
    return [k for k in keys if k not in SAFETY_KEYS]
MERIDIAN, SUNNY = "wld_seedMeridian", "wld_seedSunnyHollow"


def decisions(api: Api) -> list[dict[str, Any]]:
    assert api.rt.fake is not None
    return [json.loads(r.content) for r in api.rt.fake.requests if r.url.path.endswith("/alpha/decisions")]


def chat_caps(api: Api) -> list[int]:
    assert api.rt.fake is not None
    return [int(json.loads(r.content)["max_tokens"]) for r in api.rt.fake.requests
            if r.url.path.endswith("/chat/completions")]


def gate(api: Api, cid: str, p: float) -> None:
    assert api.rt.fake is not None
    api.rt.fake.answer_question(f"docs:{cid}", {"type": "noul", "noul": p})


def rows(msg: dict[str, Any], qid: str) -> list[dict[str, Any]]:
    return [r for r in (msg.get("trace") or {}).get("system1", {}).get("questions", []) if r["id"] == qid]


async def agent(api: Api, mode: str, cast: list[str], world: str = MERIDIAN) -> str:
    await api.set_key()
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": "agent"})).status_code == 204
    sid: str = (await create(api, mode, cast, world=world))["session"]["id"]
    await api.drive(6000)
    return sid


async def send(api: Api, sid: str, text: str, ms: float = 15000, mentions: list[str] | None = None) -> list[dict[str, Any]]:
    before = len(chars(await messages(api, sid)))
    await command(api, sid, "send", {"text": text, **({"mentions": mentions} if mentions else {})})
    await api.drive(ms)
    return chars(await messages(api, sid))[before:]


# ── 4.1 the titles and the state ──
async def test_titles_are_read_per_character_newest_first(api: Api) -> None:
    got = await document_titles(api.rt, MERIDIAN, [AMARA, MEI, VICTOR])
    assert got[AMARA] == ["ED triage guidelines", "Meridian Shift Fatigue Review 2025"]   # no extension, newest first
    assert set(got) == {AMARA, MEI, VICTOR}
    assert await document_titles(api.rt, SUNNY, [RIN, TAKESHI]) == {}
    assert await document_titles(api.rt, SUNNY, [AMARA]) == {}                            # bound to the world


def test_the_state_keeps_the_cap_and_reports_dropped_gates() -> None:
    cands = [Candidate(id=f"c{i}", name=f"Character {i}", about_source="A long-winded person. " * 40,
                     turns_since=i) for i in range(6)]
    docs = {f"c{i}": [f"A very long document title number {j} about rota rules and night cover" for j in range(10)]
            for i in range(6)}
    inp = PlanStateInput(mode="group", user_name="Kai", candidates=cands, documents=docs, latest="x " * 900,
                         recent=[{"speaker": "Kai", "text": "y " * 400} for _ in range(6)])
    st = build_turn_plan_state(inp)
    assert st.tokens <= LIMIT
    assert st.dropped_gates                                      # the cap bit: gates go first, never the cast
    assert all(c not in st.state.get("quoted_documents", {}) for c in st.dropped_gates)
    assert gates.gated([c.id for c in cands], docs, st.dropped_gates) == [c.id for c in cands
                                                                          if c.id not in st.dropped_gates]


# ── 4.2 1:1 ──
async def test_a_one_on_one_request_holds_the_three_gate_questions(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    await send(api, sid, "What does the review say about rest days?")
    [body] = [b for b in decisions(api) if f"emotion_reply:{AMARA}" in b["questions"]]
    assert unsafe_free(body["questions"]) == [f"emotion_reply:{AMARA}", f"docs:{AMARA}", "standalone", "english"]
    assert body["state"]["quoted_documents"] == {"Amara Okafor": ["ED triage guidelines",
                                                                  "Meridian Shift Fatigue Review 2025"]}
    instructions = body["questions"][f"docs:{AMARA}"]["instructions"]
    assert instructions.startswith("Does Amara Okafor's next line need facts that Amara Okafor's own documents")


async def test_the_gate_decides_the_branch(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    caps = rt_caps(api)
    gate(api, AMARA, 0.8)
    [deep] = await send(api, sid, "What does the review say about rest days?")
    [row] = rows(deep, "docs")
    assert (row["answer"], row["result"], row["action"], row["about"]) == ("yes", "used", "search the documents", AMARA)
    assert [c["name"] for c in row["compared"]] == ["t_gate", "t_confident"]
    assert chat_caps(api)[-1] == caps["deep"]
    gate(api, AMARA, 0.1)
    [quick] = await send(api, sid, "How was your day?")
    assert rows(quick, "docs")[0]["answer"] == "no" and chat_caps(api)[-1] == caps["quick"]
    assert [r["result"] for r in rows(quick, "standalone")] == ["not_used"]   # no rewrite considered on a quick turn


def rt_caps(api: Api) -> dict[str, int]:
    c = api.rt.runtime_cfg.runtime.reply_max_tokens
    return {"quick": c.one_on_one, "deep": c.one_on_one_deep}


async def test_a_late_plan_is_quick_with_a_fallback_row(api: Api) -> None:
    from tests.sessions.test_deep_m12 import measured_deadlines

    measured_deadlines(api)          # D-113: with `docsWaitAll` on, a documents plan is waited for (test_waits_u62)
    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.9)
    assert api.rt.fake is not None
    release = api.rt.fake.park_question(f"docs:{AMARA}")
    await command(api, sid, "send", {"text": "What does the review say about rest days?"})
    await api.drive(3000)
    release.set()
    await api.drive(15000)
    reply = chars(await messages(api, sid))[-1]
    [row] = rows(reply, "docs")
    assert row["result"] == "fallback" and row["action"] == "quick reply"
    assert chat_caps(api)[-1] == rt_caps(api)["quick"]
    assert any(c.get("fallback") for c in reply["trace"]["calls"] if c["purpose"] == "turn_plan")


async def test_a_character_without_sources_gets_no_gate(api: Api) -> None:
    sid = await agent(api, "one_on_one", [RIN], world=SUNNY)
    [reply] = await send(api, sid, "What does the guide say?")
    [body] = [b for b in decisions(api) if f"emotion_reply:{RIN}" in b["questions"]]
    assert unsafe_free(body["questions"]) == [f"emotion_reply:{RIN}"] and "quoted_documents" not in body["state"]
    assert not rows(reply, "standalone")
    # U-49: the question not asked is a greyed row with its reason
    assert [(r["result"], r["action"]) for r in rows(reply, "docs")] == [("skipped", gates.SKIP_NO_DOCS)]


# ── 4.3 the cast plan ──
async def test_group_first_asks_each_gated_candidate_and_uses_only_the_speakers(api: Api) -> None:
    sid = await agent(api, "group", [AMARA, MEI, VICTOR])
    assert api.rt.fake is not None
    api.rt.fake.answer_question("who_first", {"type": "choice", "choice": MEI, "confidence": 0.9,
                                              "probabilities": {MEI: 0.9}})
    gate(api, MEI, 0.7)
    gate(api, AMARA, 0.9)
    replies = await send(api, sid, "What do your notes say about the night rota?", 20000)
    first = replies[0]
    assert first["author"]["characterId"] == MEI
    docs = {r["about"]: r for r in rows(first, "docs")}
    assert docs[MEI]["result"] == "used" and docs[MEI]["answer"] == "yes"
    assert docs[AMARA]["result"] == "not_used" and docs[VICTOR]["result"] == "not_used"
    assert [r["result"] for r in rows(first, "standalone")] == ["used"]


async def test_next_speaker_asks_docs_only(api: Api) -> None:
    sid = await agent(api, "group", [AMARA, MEI, VICTOR])
    await send(api, sid, "Hello all.", 20000)
    await command(api, sid, "next-speaker")
    await api.drive(15000)
    nxt = [b for b in decisions(api) if "who_next" in b["questions"]]
    assert nxt, "a Next speaker plan was asked"
    assert {k for k in nxt[-1]["questions"] if k.startswith("docs:")} and "standalone" not in nxt[-1]["questions"]


def test_dropped_gates_go_quick_with_a_skipped_row() -> None:
    plan = CastPlan(seed="s", kind="group_first", order=[MEI],
                    gates={MEI: GateAnswer(outcome="dropped"), AMARA: GateAnswer(p=0.9)},
                    nouls=MessageNouls(standalone=0.9, english=0.9))
    tp = plan.for_speaker(MEI)
    assert tp.branch == "quick" and tp.gate is not None and tp.gate.outcome == "dropped"
    assert [(r["about"], r["result"]) for r in tp.rows if r["id"] == "docs"] == [(MEI, "skipped"), (AMARA, "not_used")]
    assert next(r for r in tp.rows if r["id"] == "docs")["action"] == gates.SKIP_TOO_LARGE     # U-49
    amara = plan.for_speaker(AMARA)
    assert amara.branch == "deep" and amara.abstain_ok   # group_first answers a user message, p ≥ t_confident


def test_who_may_abstain() -> None:
    sure = GateAnswer(p=0.9)
    assert gates.abstain_allowed(sure, "reply") and gates.abstain_allowed(sure, "second")
    for kind in ("next", "step_in", "scene", "opening", "debate", "debate_opening", "debate_ask", "greeting"):
        assert not gates.abstain_allowed(sure, kind)
    assert not gates.abstain_allowed(GateAnswer(p=0.7), "reply")


# ── 4.4 the follow plan ──
async def test_the_follow_plan_reuses_the_cast_plans_nouls(api: Api) -> None:
    sid = await agent(api, "group", [AMARA, MEI, VICTOR])
    await send(api, sid, "What do your notes say about the night rota?", 25000)
    follow = [b for b in decisions(api) if "who_second" in b["questions"]]
    assert follow
    keys = set(follow[-1]["questions"])
    assert {k for k in keys if k.startswith("docs:")} and not keys & {"standalone", "english"}


async def test_the_follow_plan_asks_the_nouls_when_the_cast_plan_didnt(api: Api) -> None:
    """A mention of Rin (no sources) asks no gate in the cast plan; Hana, who has a notebook, may follow."""
    sid = await agent(api, "group", [RIN, HANA, TAKESHI], world=SUNNY)
    await send(api, sid, "@Rin what's on the menu tonight?", 25000, mentions=[RIN])
    cast = [b for b in decisions(api) if f"emotion_reply:{RIN}" in b["questions"] and "who_second" not in b["questions"]]
    assert cast and not {k for k in cast[0]["questions"] if k.startswith("docs:") or k == "standalone"}
    follow = [b for b in decisions(api) if "who_second" in b["questions"]]
    assert follow and {f"docs:{HANA}", "standalone", "english"} <= set(follow[-1]["questions"])


# ── 4.5 the debate plan ──
async def test_a_debate_gate_back_by_the_turns_start_is_used(api: Api) -> None:
    from tests.sessions.test_debate_plan import args, debate, first_rebuttal_end, jev_answers, next_after

    sid = await debate(api)
    jev_answers(api, member_rebuttal=(MEI, 0.9))
    gate(api, AMARA, 0.9)
    assert api.rt.fake is not None
    release = api.rt.fake.park_question("member_rebuttal")
    end = await first_rebuttal_end(api, sid)
    await api.drive(800)
    nxt = next_after(await events(api, sid), end["seq"])
    assert 735 <= ms_from_iso(nxt["at"]) - ms_from_iso(end["at"]) < 745     # the member's deadline is unchanged
    release.set()                                                           # after the deadline, before the turn
    await api.drive(60000)
    amara = args(await messages(api, sid), "rebuttal")[1]
    [row] = [r for r in rows(amara, "docs") if r["about"] == AMARA]
    assert (row["result"], row["answer"]) == ("used", "yes")
    assert "t_confident" not in [c["name"] for c in row["compared"]]          # debate never abstains


async def test_a_debate_gate_later_than_the_turns_start_is_quick(api: Api) -> None:
    from tests.sessions.test_debate_plan import args, debate, first_rebuttal_end, until
    from tests.sessions.test_deep_m12 import measured_deadlines

    measured_deadlines(api)          # D-113: with `docsWaitAll` on, the turn waits for the gate
    sid = await debate(api)
    gate(api, AMARA, 0.9)
    assert api.rt.fake is not None
    release = api.rt.fake.park_question("member_rebuttal")
    end = await first_rebuttal_end(api, sid)

    async def started() -> bool:
        return any(e["type"] == "turn.start" and e["seq"] > end["seq"] for e in await events(api, sid))
    await until(api, sid, started, step=50)
    release.set()
    await api.drive(60000)
    amara = args(await messages(api, sid), "rebuttal")[1]
    [row] = [r for r in rows(amara, "docs") if r["about"] == AMARA]
    assert row["result"] == "fallback"


def test_gate_rows_compare_against_the_bank() -> None:
    row = gates.gate_row(AMARA, GateAnswer(p=0.5), purpose="turn_plan", abstain_kind=False)
    assert row["compared"] == [{"name": "t_gate", "value": 0.5, "threshold": 0.45}]
