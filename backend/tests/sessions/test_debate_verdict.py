"""The verdict (debate tasks 7.1–7.10; design D12–D16; debate-verdict spec; provider-gateway "A rubric 429"). Jev is the
fake with set score answers; DeepSeek's prose is canned JSON. No network."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from tests.conftest import Api
from tests.sessions.kit import API, assert_reduces, chars, command, create, events, ledger, messages, snapshot

AMARA, MEI, VICTOR = "chr_seedAmara", "chr_seedMei", "chr_seedVictor"
NOTE_PROSE = "The arbiter's notes couldn't be written; the summary quotes the speakers."
NOTE_SCORES = "The arbiter couldn't score this debate; here is the summary."


def prose(prop: int = 3, opp: int = 3, *, rationale: str = "The Proposition answered the strongest point directly.",
          key: str = "Whether homework builds habits or only steals rest.") -> dict[str, Any]:
    return {"content": json.dumps({"summary": {"prop": [f"Prop point {i}" for i in range(prop)],
                                               "opp": [f"Opp point {i}" for i in range(opp)]},
                                   "keyDisagreement": key, "rationale": rationale})}


async def debate(api: Api, profile: str = "agent", **cfg: Any) -> str:
    await api.set_key()
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": profile})).status_code == 204
    config = {"motion": "This house would ban homework", "format": "two_sided",
              "sides": {"prop": [AMARA], "opp": [VICTOR]}, "roundsPreset": "quick",
              "phases": ["opening", "closing"], "turnLength": "short", "moderator": "user", "verdictBy": "arbiter",
              "rubric": [], "autoAdvance": True, "pauseMs": 1500, **cfg}
    cast = [AMARA, MEI, VICTOR] if cfg.get("format") == "panel" else [AMARA, VICTOR]
    sid: str = (await create(api, "debate", cast, config=config))["session"]["id"]
    return sid


def requests(api: Api, path: str) -> list[dict[str, Any]]:
    assert api.rt.fake is not None
    return [json.loads(r.content) for r in api.rt.fake.requests if r.url.path.endswith(path)]


def rubric_requests(api: Api) -> list[dict[str, Any]]:
    return [b for b in requests(api, "/alpha/decisions") if any(k.startswith("rubric_") for k in b["questions"])]


def verdict_requests(api: Api) -> list[dict[str, Any]]:
    assert api.rt.fake is not None
    return [json.loads(r.content) for r in api.rt.fake.requests if r.url.path.endswith("/chat/completions")
            and r.headers.get("x-horizon-purpose") == "verdict"]


def jev_scores(api: Api, prop: float = 4, opp: float = 1, *, fail: int = 0, status: int = 429) -> None:
    """Jev scores every Proposition question `prop` and every Opposition one `opp` (level indexes 0–4); the first
    `fail` rubric requests answer `status` instead."""
    fake = api.rt.fake
    assert fake is not None
    plain = fake._decide
    left = [fail]

    def decide(body: dict[str, Any]) -> httpx.Response:
        qs = body.get("questions") or {}
        if any(k.startswith("rubric_") for k in qs) and left[0] > 0:
            left[0] -= 1
            return httpx.Response(status, json={"error": {"code": status, "message": "Too many requests"}})
        resp = plain(body)
        data = json.loads(resp.content)
        for key in qs:
            if key.startswith("rubric_"):
                s = prop if ":prop" in key else opp
                data["answers"][key] = {"type": "score", "score": s, "confidence": 0.9,
                                        "probabilities": {str(i): (0.9 if i == round(s) else 0.025) for i in range(5)}}
        return httpx.Response(200, json=data)

    fake._decide = decide  # type: ignore[method-assign]


def can(api: Api, *responses: dict[str, Any]) -> None:
    assert api.rt.fake is not None
    api.rt.fake.set_canned("verdict", list(responses))


def notes(msgs: list[dict[str, Any]]) -> list[str]:
    """System notes and the verdict banner."""
    return [m["content"] for m in msgs if m["kind"] in ("system_note", "verdict")]


async def verdict_of(api: Api, sid: str) -> dict[str, Any]:
    v: dict[str, Any] = (await snapshot(api, sid))["session"]["state"]["verdict"]
    return v


# ── 7.2 / 7.5: an agent Arbiter verdict ──
async def test_an_agent_arbiter_verdict_from_jevs_scores_and_canned_prose(api: Api) -> None:
    sid = await debate(api)
    jev_scores(api, prop=4, opp=1)
    can(api, prose())
    await api.drive(120000)
    v = await verdict_of(api, sid)
    assert v["decidedBy"] == "arbiter" and v["strongerCase"] == "prop" and v["scoresBy"] == "side"
    assert len(v["scores"]) == 8 and all(0 <= s["value"] <= 10 for s in v["scores"])
    assert {(s["subjectId"], s["value"]) for s in v["scores"]} == {("prop", 10.0), ("opp", 2.5)}
    assert v["summary"] == [{"subjectId": "prop", "points": ["Prop point 0", "Prop point 1", "Prop point 2"]},
                            {"subjectId": "opp", "points": ["Opp point 0", "Opp point 1", "Opp point 2"]}]
    assert v["rationale"] == "The Proposition answered the strongest point directly."
    (rq,) = rubric_requests(api)
    assert len(rq["questions"]) == 8 and isinstance(rq["state"]["quoted_sides"], list)
    assert [b["side"] for b in rq["state"]["quoted_sides"]] == ["Proposition", "Opposition"]
    (vq,) = verdict_requests(api)
    assert vq["response_format"] == {"type": "json_object"} and vq["temperature"] == 0.7 and vq["max_tokens"] == 1200
    user = vq["messages"][1]["content"]
    assert "The result: the stronger case is the Proposition's." in user
    assert user.endswith("The debate is in English. Write the notes in English.")
    msgs = await messages(api, sid)
    assert "STRONGER CASE: PROPOSITION" in notes(msgs)
    purposes = [r["purpose"] for r in await ledger(api)]
    assert purposes.count("rubric") == 1 and purposes.count("verdict") == 1
    assert {r["category"] for r in await ledger(api) if r["purpose"] == "verdict"} == {"chat"}
    await assert_reduces(api, sid)


async def test_an_unknown_criterion_is_asked_by_position_with_its_label_quoted(api: Api) -> None:
    sid = await debate(api, rubric=[{"id": "evidence", "label": "Evidence"}, {"id": "wit", "label": "Wit"}])
    jev_scores(api, prop=3, opp=3)
    can(api, prose())
    await api.drive(120000)
    (rq,) = rubric_requests(api)
    assert set(rq["questions"]) == {"rubric_evidence:prop", "rubric_evidence:opp", "rubric_generic:prop:1",
                                    "rubric_generic:opp:1"}
    assert rq["state"]["quoted_criteria"] == ["Wit"]
    assert all("Wit" not in json.dumps(q) for q in rq["questions"].values())
    v = await verdict_of(api, sid)
    assert {s["criterionId"] for s in v["scores"]} == {"evidence", "wit"} and v["strongerCase"] is None   # equal
    assert "TOO CLOSE TO CALL" in notes(await messages(api, sid))


# ── 7.3: You decide, and validation ──
async def test_you_decide_words_the_rationale_as_the_arbiters_view(api: Api) -> None:
    sid = await debate(api, verdictBy="user")
    jev_scores(api, prop=1, opp=4)
    can(api, prose(rationale="The arbiter's scores favoured the Opposition: it answered every point."))
    await api.drive(120000)
    (vq,) = verdict_requests(api)
    assert "starting \"The arbiter's scores favoured the Opposition: …\"" in vq["messages"][0]["content"]
    await command(api, sid, "debate/pick", {"side": "prop"})
    await api.drive(1000)
    v = await verdict_of(api, sid)
    assert v["decidedBy"] == "user" and v["strongerCase"] == "prop" and len(v["scores"]) == 8
    assert v["rationale"].startswith("The arbiter's scores favoured the Opposition")
    assert "STRONGER CASE: PROPOSITION" in notes(await messages(api, sid))
    await assert_reduces(api, sid)


async def test_too_many_points_keeps_the_first_five(api: Api) -> None:
    sid = await debate(api)
    jev_scores(api)
    can(api, prose(prop=7))
    await api.drive(120000)
    v = await verdict_of(api, sid)
    assert v["summary"][0]["points"] == [f"Prop point {i}" for i in range(5)]


# ── 7.4: the failure table ──
async def test_the_prose_fails_the_scores_stand_with_a_quoted_summary(api: Api) -> None:
    sid = await debate(api)
    jev_scores(api)
    can(api, {"content": "not json"}, {"content": "still not json"})
    await api.drive(120000)
    v = await verdict_of(api, sid)
    assert v["decidedBy"] == "arbiter" and v["strongerCase"] == "prop" and len(v["scores"]) == 8
    assert "rationale" not in v and "keyDisagreement" not in v
    args = [m["content"] for m in chars(await messages(api, sid))]
    assert all(any(a.startswith(p.rstrip(".")[:20]) for a in args) for p in v["summary"][0]["points"])
    assert NOTE_PROSE in notes(await messages(api, sid))
    assert len(verdict_requests(api)) == 2                   # one paid retry


async def test_scores_fail_under_arbiter_give_a_summary_only(api: Api) -> None:
    """The rubric's 429 is retried once after 1 s; failing again, the verdict is summary only (SUMMARY)."""
    sid = await debate(api)
    jev_scores(api, fail=2)
    can(api, prose())
    await api.drive(120000)
    v = await verdict_of(api, sid)
    assert v["decidedBy"] == "none" and v["strongerCase"] is None and "scores" not in v
    msgs = await messages(api, sid)
    assert "SUMMARY" in notes(msgs) and NOTE_SCORES in notes(msgs)
    assert len(rubric_requests(api)) == 2
    (vq,) = verdict_requests(api)
    assert "The result: summary only, no scores and no winner." in vq["messages"][1]["content"]


async def test_a_rubric_429_is_retried_once_after_one_second(api: Api) -> None:
    sid = await debate(api)
    jev_scores(api, fail=1)
    can(api, prose())
    await api.drive(120000)
    v = await verdict_of(api, sid)
    assert v["decidedBy"] == "arbiter" and len(v["scores"]) == 8 and len(rubric_requests(api)) == 2


async def test_scores_fail_under_you_decide_give_the_pick_alone(api: Api) -> None:
    sid = await debate(api, verdictBy="user")
    jev_scores(api, fail=2)
    can(api, prose())
    await api.drive(120000)
    await command(api, sid, "debate/pick", {"side": "opp"})
    await api.drive(1000)
    v = await verdict_of(api, sid)
    assert v["decidedBy"] == "user" and v["strongerCase"] == "opp" and "scores" not in v and "rationale" not in v
    assert NOTE_SCORES in notes(await messages(api, sid))


async def test_both_fail_give_a_quoted_summary_and_both_notes(api: Api) -> None:
    sid = await debate(api)
    jev_scores(api, fail=2)
    can(api, {"content": "x"}, {"content": "y"})
    await api.drive(120000)
    v = await verdict_of(api, sid)
    assert v["decidedBy"] == "none" and "scores" not in v
    msgs = await messages(api, sid)
    assert NOTE_SCORES in notes(msgs) and NOTE_PROSE in notes(msgs) and "SUMMARY" in notes(msgs)


@pytest.mark.parametrize("how", ["last_closing", "end_now"])
async def test_the_cap_refusal_hang_is_gone(api: Api, monkeypatch: Any, how: str) -> None:
    """The verdict work is refused by the daily cap (set as the work starts): the session pauses with no verdict;
    raised and resumed, the work runs again and the debate ends with a verdict. `end_now`: End → "Go to verdict now"
    during the opening, so the refusal lands in the verdict phase (the old hang)."""
    from horizon.sessions import debate_verdict

    sid = await debate(api, autoAdvance=True)
    jev_scores(api)
    can(api, prose())
    plain = debate_verdict.start
    capped = [False]

    def start(actor: Any) -> Any:
        if not capped[0]:
            capped[0] = True
            from dataclasses import replace

            low = replace(api.rt.gateway.caps(), daily_cap_usd=0.00001)
            monkeypatch.setattr(api.rt.gateway, "caps", lambda: low)
        return plain(actor)

    monkeypatch.setattr(debate_verdict, "start", start)
    if how == "end_now":
        await api.drive(3000)
        await command(api, sid, "debate/end", {"withVerdict": True})
    await api.drive(60000)
    snap = await snapshot(api, sid)
    assert capped[0] and snap["session"]["status"] == "paused" and not snap["session"]["state"].get("verdict")
    assert snap["session"]["state"]["phase"] == ("verdict" if how == "end_now" else "closing")
    monkeypatch.undo()
    assert (await api.client.patch(f"{API}/settings", json={"budget": {"dailyCapUsd": 5.0}})).status_code == 200
    await command(api, sid, "debate/resume")
    await api.drive(30000)
    snap = await snapshot(api, sid)
    assert snap["session"]["status"] == "ended" and snap["session"]["state"]["verdict"]["decidedBy"] == "arbiter"
    await assert_reduces(api, sid)


# ── 7.6: naive's single call ──
async def test_the_yardsticks_verdict_is_one_call_used_as_written(api: Api) -> None:
    sid = await debate(api, "naive")
    scores = {s: {c: v for c in ("evidence", "rebuttal", "clarity", "persuasion")} for s, v in (("prop", 6.0),
                                                                                             ("opp", 7.5))}
    body = json.loads(prose()["content"])
    can(api, {"content": json.dumps({**body, "scores": scores, "strongerCase": "prop"})})
    await api.drive(120000)
    v = await verdict_of(api, sid)
    assert v["strongerCase"] == "prop"                      # DeepSeek's own call, even against its scores (D15)
    assert {(s["subjectId"], s["value"]) for s in v["scores"]} == {("prop", 6.0), ("opp", 7.5)}
    assert len(verdict_requests(api)) == 1 and rubric_requests(api) == []
    assert "First score each side from 0 to 10" in verdict_requests(api)[0]["messages"][0]["content"]


async def test_a_naive_panel_maps_names_to_ids(api: Api) -> None:
    sid = await debate(api, "naive", format="panel", sides=None)
    can(api, {"content": json.dumps({"summary": {AMARA: ["a", "b"], MEI: ["c", "d"], VICTOR: ["e", "f"]},
                                     "keyDisagreement": "Rest or habit.", "rationale": "Three views."})})
    await api.drive(150000)
    v = await verdict_of(api, sid)
    assert {x["subjectId"] for x in v["summary"]} == {AMARA, MEI, VICTOR} and "scores" not in v
    sysmsg = verdict_requests(api)[0]["messages"][0]["content"]
    assert f'→ "{AMARA}"' in sysmsg


# ── 7.7 / 7.8: when the work runs, and the pick ──
async def test_end_right_after_the_last_closing_pays_once(api: Api) -> None:
    sid = await debate(api)
    jev_scores(api)
    can(api, prose())

    async def closings_done() -> bool:
        cl = [m for m in chars(await messages(api, sid)) if m["debate"]["phase"] == "closing"]
        evs = await events(api, sid)
        return len(cl) == 2 and any(e["type"] == "turn.end" and e["payload"]["messageId"] == cl[1]["id"] for e in evs)
    while not await closings_done():
        await api.drive(20)
    await api.drive(200)                                      # inside the pause
    await command(api, sid, "debate/end", {"withVerdict": True})
    await api.drive(60000)
    assert len(rubric_requests(api)) == 1 and len(verdict_requests(api)) == 1
    assert (await verdict_of(api, sid))["decidedBy"] == "arbiter"
    await assert_reduces(api, sid)


async def test_extend_after_the_last_closing_discards_the_work(api: Api) -> None:
    sid = await debate(api)
    jev_scores(api)
    can(api, prose())
    assert api.rt.fake is not None
    release = api.rt.fake.park_question("rubric_")

    async def parked() -> bool:
        return api.rt.fake.decision_parked.is_set()  # type: ignore[union-attr]
    while not await parked():
        await api.drive(20)
    await command(api, sid, "debate/extend-round")
    await api.drive(200)
    release.set()
    await api.drive(120000)
    rows = [r for r in await ledger(api) if r["purpose"] == "rubric"]
    assert rows[0]["finish_reason"] == "cancelled" and len(rubric_requests(api)) == 2
    cl = [m for m in chars(await messages(api, sid)) if m["debate"]["phase"] == "closing"]
    assert len(cl) == 4 and (await verdict_of(api, sid))["decidedBy"] == "arbiter"


async def test_a_click_before_the_work_is_done_is_answered_at_once(api: Api) -> None:
    sid = await debate(api, verdictBy="user")
    jev_scores(api)
    can(api, prose())
    assert api.rt.fake is not None
    release = api.rt.fake.park_question("rubric_")
    while not api.rt.fake.decision_parked.is_set():
        await api.drive(20)
    await api.drive(5000)
    r = await api.post(f"{API}/sessions/{sid}/debate/pick", {"side": "prop"})
    assert r.status_code == 202
    assert not (await snapshot(api, sid))["session"]["state"].get("verdict")
    assert (await api.post(f"{API}/sessions/{sid}/debate/pause", {})).status_code == 202
    release.set()
    await api.drive(30000)
    v = await verdict_of(api, sid)
    assert v["decidedBy"] == "user" and v["strongerCase"] == "prop"
    await assert_reduces(api, sid)


# ── 7.10: scripted ──
async def test_scripted_keeps_the_mock_verdict_charged_as_chat(api: Api) -> None:
    sid = await debate(api, "scripted")
    await api.drive(120000)
    v = await verdict_of(api, sid)
    assert v["decidedBy"] == "arbiter"
    rows = [r for r in await ledger(api) if r["purpose"] == "verdict"]
    assert len(rows) == 1 and rows[0]["category"] == "chat"
    assert rubric_requests(api) == [] and verdict_requests(api) == []


# ── 7.9: the resume rule on the first command after a load ──
async def test_a_pick_after_an_idle_release_runs_the_work_again(api: Api) -> None:
    sid = await debate(api, verdictBy="user")
    jev_scores(api)
    can(api, prose())
    await api.drive(60000)
    assert (await snapshot(api, sid))["session"]["state"]["phase"] == "verdict"
    assert (await api.client.post(f"{API}/sessions/{sid}/leave")).status_code == 204
    await api.drive(11 * 60_000)
    assert api.rt.sessions.peek(sid) is None                 # released: the work and any pick are gone
    await command(api, sid, "debate/pick", {"side": "opp"})
    await api.drive(30000)
    v = await verdict_of(api, sid)
    assert v["decidedBy"] == "user" and v["strongerCase"] == "opp" and len(v["scores"]) == 8
    assert len(rubric_requests(api)) == 2                    # the first work, and its re-run after the load
    await assert_reduces(api, sid)
