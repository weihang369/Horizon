"""The cast plan: Jev call 1 for group and watch turns (group-watch task 2.3, 2.4; design D3–D7, D11, D13, D14, D22;
turn-plan "The cast plan for group and watch", "Who-speaks fallbacks"; watch-direction "The steer")."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any

from horizon.ai.agent.cast_plan import least_recent, pick_who, steer_rule
from horizon.ai.agent.planner import JevTurnPlanner
from horizon.ai.contexts import CastPlan, CastRequest, CharacterView, MessageView, ParticipantView, SessionContext, WorldView
from horizon.ai.decider import ChoiceAnswer, Decider
from horizon.domain.clock import FrozenClock, calendar_for
from horizon.gateway.errors import ProviderError
from tests.unit.test_planner import T0, TIMEOUTS, Deps, Jev

CAST = ["chr_a", "chr_b", "chr_c"]
NAMES = {"chr_a": "Amara Okafor", "chr_b": "Mei Lin", "chr_c": "Victor Hale"}
PROFILES = [CharacterView(id=c, name=n, profile={"personality": {"summary": f"{n} is calm. Dry humour."}})
            for c, n in NAMES.items()]


class Db:
    class _Conn:
        async def execute(self, *_: Any) -> Any:
            class R:
                def first(self) -> tuple[str, float, int]:
                    return ("typesafe/jev-1.13", 0.00005, 451)
            return R()

    def read(self) -> Any:
        conn = self._Conn()

        class Cm:
            async def __aenter__(self) -> Any:
                return conn

            async def __aexit__(self, *_: Any) -> None:
                return None
        return Cm()


class CastDeps(Deps):
    def gateway(self) -> Any:
        return type("Gw", (), {"ledger": type("L", (), {"db": Db()})})()


def session(mode: str = "group", premise: str = "") -> SessionContext:
    recent = [MessageView(id="m1", seq=1, author_type="character", character_id="chr_c", name="Victor Hale",
                          kind="chat", content="Long day at the shop."),
              MessageView(id="m2", seq=2, author_type="user", name="Kai", kind="chat", content="Mei, is it worth it?")]
    return SessionContext(
        session_id="ses_1", seed="s1", world=WorldView(id="w", name="Meridian", you={"displayName": "Kai"}), mode=mode,
        title="t", recent=recent, config={"premise": premise} if premise else None,
        participants=[ParticipantView(character_id=c, name=n, role="speaker", character_role="Florist", emotion="neutral",
                                      energy={"current": 500}) for c, n in NAMES.items()])


def request(clock: FrozenClock, kind: str = "group_first", **kw: Any) -> CastRequest:
    base: dict[str, Any] = {"session": session("watch" if kind in ("scene", "opening") else "group",
                                               premise="A storm traps them in the shop."),
                            "kind": kind, "candidates": CAST, "cast": PROFILES, "latest": "Mei, is it worth it?",
                            "turn_index": 4, "base_faces": {c: "neutral" for c in CAST},
                            "turns_since": {"chr_a": 2, "chr_b": None, "chr_c": 0}, "started_at": clock.now()}
    base.update(kw)
    return CastRequest(**base)


def make(answers: Mapping[str, Any] | None = None, *, delay_s: float | None = 0.1,
         error: ProviderError | None = None) -> tuple[JevTurnPlanner, Jev, FrozenClock]:
    clock = FrozenClock(calendar_for("Asia/Kuala_Lumpur"), T0)
    jev = Jev(clock, answers, delay_s, error)
    d = Decider(jev, TIMEOUTS, None, clock=clock, spawn=clock.activity.spawn)
    return JevTurnPlanner(CastDeps(d)), jev, clock


async def run(planner: JevTurnPlanner, clock: FrozenClock, req: CastRequest, advance_ms: float = 800) -> CastPlan:
    task = clock.activity.spawn("plan", planner.plan_cast(req))
    await asyncio.sleep(0)
    await clock.advance(advance_ms)
    plan = await task
    assert plan is not None
    return plan


def choice(c: str, conf: float, **probs: float) -> dict[str, Any]:
    return {"type": "choice", "choice": c, "confidence": conf, "probabilities": probs or {c: conf}}


def faces(face: str = "happy", conf: float = 0.8, qid: str = "emotion_reply", ids: list[str] = CAST) -> dict[str, Any]:
    return {f"{qid}:{c}": choice(face, conf) for c in ids}


# ── the pure rules ──
def test_least_recent_puts_never_spoken_first_then_the_longest_ago() -> None:
    assert least_recent(CAST, {"chr_a": 2, "chr_b": None, "chr_c": 0}) == "chr_b"
    assert least_recent(CAST, {"chr_a": 2, "chr_b": 5, "chr_c": 0}) == "chr_b"
    assert least_recent(["chr_a", "chr_c"], {"chr_a": 0, "chr_c": 0}) == "chr_a"   # cast order breaks a tie


def test_unsure_takes_the_least_recent_of_the_top_two() -> None:
    a = ChoiceAnswer("chr_a", 0.3, {"chr_a": 0.4, "chr_c": 0.35, "chr_b": 0.25})
    assert pick_who(a, CAST, floor=0.6, turns_since={"chr_a": 0, "chr_b": None, "chr_c": 3}) == ("chr_c", "below_floor", 0.3)


def test_the_steer_rule() -> None:
    assert steer_rule(0.9, 0.8, None).steer and steer_rule(0.9, 0.8, None).action == "steer"
    assert steer_rule(0.9, 0.8, "recent").action == "no steer (steered recently)"
    assert steer_rule(0.9, 0.8, "note").action == "no steer (director's note)"
    assert not steer_rule(0.5, 0.8, None).steer and steer_rule(None, 0.8, None).action == "no steer"


# ── the request and the plan ──
async def test_group_first_slot_asks_who_and_every_face_in_one_request() -> None:
    planner, jev, clock = make({"who_first": choice("chr_b", 0.8, chr_b=0.7, chr_a=0.2, chr_c=0.1), **faces()})
    plan = await run(planner, clock, request(clock))
    assert len(jev.sent) == 1
    assert set(jev.sent[0]) == {"who_first", "emotion_reply:chr_a", "emotion_reply:chr_b", "emotion_reply:chr_c"}
    assert "none" not in jev.sent[0]["who_first"]["criteria"]
    assert plan.order == ["chr_b"] and plan.who is not None and plan.who.source == "jev"
    assert plan.who.candidates[0] == {"characterId": "chr_b", "p": 0.7}
    assert plan.calls == [{"purpose": "turn_plan", "model": "typesafe/jev-1.13", "costUsd": 5e-05, "latencyMs": 451}]
    tp = plan.for_speaker("chr_b")
    who_row = next(r for r in tp.rows if r["id"] == "who_first")
    assert (who_row["purpose"], who_row["answer"], who_row["result"], who_row["action"]) == (
        "turn_plan", "chr_b", "used", "answers first")
    results = {r["about"]: r["result"] for r in tp.rows if r["id"] == "emotion_reply"}
    assert results == {"chr_a": "not_used", "chr_b": "used", "chr_c": "not_used"}
    assert tp.emotion is not None and tp.emotion.face == "happy" and tp.emotion.source == "classifier"


async def test_energy_never_reaches_jev() -> None:
    """G9 (task 2.4): the state carries no energy, whatever the candidates' energy is."""
    planner, jev, clock = make({"who_first": choice("chr_a", 0.9), **faces()})
    await run(planner, clock, request(clock))
    text = json.dumps(jev.states[0]).lower()
    assert "energy" not in text and "tired" not in text and "500" not in text
    assert set(jev.states[0]) <= {"mode", "quoted_user", "quoted_cast", "quoted_latest", "quoted_recent"}


async def test_unsure_pick_takes_the_least_recent_of_the_top_two() -> None:
    # under who_first's measured floor (0.2, task 10.3)
    planner, _, clock = make({"who_first": choice("chr_c", 0.15, chr_c=0.4, chr_a=0.35, chr_b=0.25), **faces()})
    plan = await run(planner, clock, request(clock))
    assert plan.order == ["chr_a"] and plan.who is not None and plan.who.source == "below_floor"
    row = plan.shared_rows[0]
    assert row["result"] == "below_threshold" and row["compared"][0]["value"] == 0.15


async def test_late_answer_falls_back_to_the_least_recently_spoken() -> None:
    planner, _, clock = make(delay_s=None)
    plan = await run(planner, clock, request(clock))
    assert plan.order == ["chr_b"] and plan.who is not None and plan.who.source == "late"
    assert plan.who.reason == "fallback" and plan.calls[0]["fallback"] is True
    assert plan.shared_rows[0]["result"] == "fallback" and "p" not in plan.shared_rows[0]
    assert all(f.outcome == "late" for f in plan.faces.values())


async def test_a_rate_limit_falls_back_at_once() -> None:
    planner, _, clock = make(error=ProviderError("rate_limited", "429"))
    plan = await run(planner, clock, request(clock), advance_ms=10)
    assert plan.order == ["chr_b"] and plan.who is not None and plan.who.source == "fallback"


async def test_an_invalid_pick_falls_back() -> None:
    planner, _, clock = make({"who_first": choice("chr_nobody", 0.9), **faces()})
    plan = await run(planner, clock, request(clock))
    assert plan.order == ["chr_b"] and plan.who is not None and plan.who.source == "fallback"


async def test_a_single_candidate_is_not_asked_who_but_its_face_is() -> None:
    planner, jev, clock = make(faces(ids=["chr_a"]))
    plan = await run(planner, clock, request(clock, candidates=["chr_a"]))
    assert list(jev.sent[0]) == ["emotion_reply:chr_a"] and plan.order == ["chr_a"]
    assert plan.who is not None and plan.who.source == "single" and plan.shared_rows == []


async def test_mentions_ask_only_their_faces() -> None:
    planner, jev, clock = make(faces(ids=["chr_c"]))
    plan = await run(planner, clock, request(clock, kind="group_mentioned", forced=["chr_c"], forced_by="mention"))
    assert list(jev.sent[0]) == ["emotion_reply:chr_c"] and plan.order == ["chr_c"]
    assert plan.who is not None and plan.who.forced_by == "mention"


async def test_everyone_orders_by_probability() -> None:
    planner, _, clock = make({"who_first": choice("chr_c", 0.5, chr_c=0.5, chr_a=0.3, chr_b=0.2), **faces()})
    plan = await run(planner, clock, request(clock, kind="everyone"))
    assert plan.order == ["chr_c", "chr_a", "chr_b"] and plan.shared_rows[0]["action"] == "sets the order"
    tp = plan.for_speaker("chr_a")
    assert [r.get("about") for r in tp.rows if r["id"] == "emotion_reply"] == ["chr_a"]


async def test_everyone_falls_back_to_cast_order() -> None:
    planner, _, clock = make(delay_s=None)
    plan = await run(planner, clock, request(clock, kind="everyone"))
    assert plan.order == CAST


async def test_a_watch_turn_asks_who_faces_and_talk_finished() -> None:
    answers = {"who_scene": choice("chr_a", 0.9), **faces(qid="emotion_line", ids=["chr_a", "chr_b"]),
               "talk_finished": {"type": "noul", "noul": 0.92}}
    planner, jev, clock = make(answers)
    plan = await run(planner, clock, request(clock, kind="scene", candidates=["chr_a", "chr_b"],
                                             latest="Victor Hale: Long day at the shop."))
    assert set(jev.sent[0]) == {"who_scene", "emotion_line:chr_a", "emotion_line:chr_b", "talk_finished"}
    assert jev.states[0]["quoted_premise"] == "A storm traps them in the shop."
    assert plan.steer and plan.for_speaker("chr_a").cue == "steer"
    talk = next(r for r in plan.shared_rows if r["id"] == "talk_finished")
    assert (talk["answer"], talk["result"], talk["action"]) == ("yes", "used", "steer")


async def test_a_guard_turn_asks_no_who_question() -> None:
    answers = {**faces(qid="emotion_line", ids=["chr_b"]), "talk_finished": {"type": "noul", "noul": 0.95}}
    planner, jev, clock = make(answers)
    plan = await run(planner, clock, request(clock, kind="scene", forced=["chr_b"], forced_by="round_order",
                                             reason="Mei hadn't spoken for 6 turns.", steer_block="recent",
                                             latest="Victor Hale: Long day at the shop."))
    assert set(jev.sent[0]) == {"emotion_line:chr_b", "talk_finished"}
    assert plan.order == ["chr_b"] and plan.who is not None and plan.who.forced_by == "round_order"
    assert not plan.steer and plan.talk is not None and plan.talk.action == "no steer (steered recently)"
    assert not [r for r in plan.shared_rows if r["id"] == "who_scene"]


async def test_the_opening_asks_the_opening_face_and_no_talk_question() -> None:
    planner, jev, clock = make({"who_scene": choice("chr_a", 0.9), **faces(qid="emotion_opening")})
    plan = await run(planner, clock, request(clock, kind="opening", latest=""))
    assert set(jev.sent[0]) == {"who_scene", *(f"emotion_opening:{c}" for c in CAST)}
    assert "quoted_latest" not in jev.states[0] and plan.talk is None


async def test_a_late_talk_question_never_steers() -> None:
    planner, _, clock = make(delay_s=None)
    plan = await run(planner, clock, request(clock, kind="scene", latest="Victor Hale: Hm."))
    assert not plan.steer and plan.talk is not None and plan.talk.action == "no steer"
    assert next(r for r in plan.shared_rows if r["id"] == "talk_finished")["result"] == "fallback"
