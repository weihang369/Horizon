"""The rubric and the prose, offline (debate tasks 7.2, 7.3; design D12, D13; debate-verdict "A near tie", "The worst
case fits", "A swapped order is a different request", "Too many points")."""

from __future__ import annotations

import json

import pytest

from horizon.ai.agent import rubric
from horizon.ai.contexts import DebateLine, ParticipantView, SessionContext, VerdictRequest, WorldView
from horizon.ai.naive import verdict as prose
from horizon.evals.store import jev_key

NAMES = ["Amara Okafor", "Mei Lin", "Rin Takeda", "Victor Hale", "Jo Park"]


def session(n_prop: int = 1, n_opp: int = 1, rubric_cfg: list[dict[str, str]] | None = None) -> SessionContext:
    parts = [ParticipantView(character_id=f"c{i}", name=NAMES[i], role="speaker", energy={"current": 500},
                             side="prop" if i < n_prop else "opp") for i in range(n_prop + n_opp)]
    return SessionContext(session_id="s", seed="seed", world=WorldView(id="w", name="M", you={"displayName": "Kai"}),
                          mode="debate", title="t", participants=parts, recent=[],
                          config={"motion": "This house would ban homework", "format": "two_sided",
                                  "rubric": rubric_cfg or []})


def line(i: int, phase: str = "opening", it: int = 1, side: str = "prop", text: str = "Homework steals rest. And more.",
         kind: str = "argument") -> DebateLine:
    return DebateLine(kind=kind, phase=phase, iteration=it, side=side, speaker=NAMES[i], character_id=f"c{i}",  # type: ignore[arg-type]
                      text=text)


def req(lines: list[DebateLine], **kw: object) -> VerdictRequest:
    return VerdictRequest(session=kw.pop("session", session()), by=str(kw.pop("by", "arbiter")), lines=lines,  # type: ignore[arg-type]
                          **kw)  # type: ignore[arg-type]


def test_the_default_rubric_asks_eight_score_questions_keyed_by_side() -> None:
    r = req([line(0), line(1, side="opp")])
    crit = rubric.criteria({})
    qs = rubric.questions(r, crit)
    assert sorted(qs) == sorted(f"rubric_{c}:{s}" for c in ("evidence", "rebuttal", "clarity", "persuasion")
                                for s in ("prop", "opp"))
    assert "Proposition" in qs["rubric_evidence:prop"].instructions
    assert "Opposition" in qs["rubric_evidence:opp"].instructions


def test_an_unknown_criterion_is_asked_by_position() -> None:
    crit = rubric.criteria({"rubric": [{"id": "wit", "label": "Wit"}, {"id": "clarity", "label": "Clarity"},
                                       {"id": "grace", "label": "Grace"}]})
    assert [(c.qid, c.n) for c in crit] == [("rubric_generic", 1), ("rubric_clarity", None), ("rubric_generic", 2)]
    r = req([line(0), line(1, side="opp")], session=session(rubric_cfg=[{"id": "wit", "label": "Wit"},
                                                                         {"id": "grace", "label": "Grace"}]))
    st = rubric.state_for(r, rubric.criteria(r.session.config or {}))
    assert st["quoted_criteria"] == ["Wit", "Grace"]
    qs = rubric.questions(r, rubric.criteria(r.session.config or {}))
    assert "numbered 2" in qs["rubric_generic:opp:2"].instructions
    assert all("Wit" not in q.instructions and "Grace" not in q.instructions for q in qs.values())


def test_bars_are_unit_times_ten_and_a_near_tie_is_too_close() -> None:
    from horizon.ai.decider import ScoreAnswer

    crit = rubric.criteria({})
    answers = {c.key(s): ScoreAnswer(score=3 if s == "prop" else 2) for c in crit for s in ("prop", "opp")}
    bars = rubric.bars(answers, crit)
    assert bars is not None and {(b["subjectId"], b["value"]) for b in bars} == {("prop", 7.5), ("opp", 5.0)}
    means, stronger = rubric.decide([{"subjectId": "prop", "value": 6.4}, {"subjectId": "opp", "value": 6.1}], 0.5)
    assert stronger is None and means == {"prop": 6.4, "opp": 6.1}
    assert rubric.decide([{"subjectId": "prop", "value": 6.0}, {"subjectId": "opp", "value": 6.6}], 0.5)[1] == "opp"
    assert rubric.margin() == 0.25   # verdict.margin, chosen on the debate suite's dev split (task 10.8)
    fb = {**answers, crit[0].key("prop"): ScoreAnswer(score=2, source="fallback")}
    assert rubric.bars(fb, crit) is None


def test_a_lead_of_exactly_the_margin_wins() -> None:
    # 15.9 / 4 - 16.9 / 4 is -0.24999999999999956 in floats: the bars' one decimal decides, not the float error
    def side(s: str, *values: float) -> list[dict[str, object]]:
        return [{"subjectId": s, "value": v} for v in values]

    prop = side("prop", 2.7, 3.4, 8.6, 1.2)
    assert rubric.decide(prop + side("opp", 2.7, 3.4, 8.6, 2.2), 0.25)[1] == "opp"
    assert rubric.decide(prop + side("opp", 2.7, 3.4, 8.6, 2.1), 0.25)[1] is None


def test_the_worst_case_fits_or_is_summary_only() -> None:
    """5 debaters, 4 extensions per phase (5 iterations), every argument at the long cap, 10 Asks."""
    long_text = " ".join(f"word{i}" for i in range(380))   # ≈ the 480-token long cap
    lines: list[DebateLine] = []
    for phase in ("opening", "rebuttal", "closing"):
        for it in range(1, 6):
            for i in range(5):
                lines.append(line(i, phase, it, "prop" if i < 3 else "opp", long_text))
    for k in range(10):
        lines.append(DebateLine(kind="question", phase="rebuttal", text=f"Question {k}?"))
        lines.append(line(k % 5, "rebuttal", 1, "prop" if k % 5 < 3 else "opp", long_text, kind="answer"))
    r = req(lines, session=session(3, 2))
    crit = rubric.criteria({})
    fitted = rubric.budgeted(r, crit)
    if fitted is None:
        assert rubric.tokens(rubric.state_for(r, crit, 2)) > rubric.STATE_MAX
    else:
        state, cut = fitted
        assert cut >= 1 and rubric.tokens(state, rubric.questions(r, crit)) < 30000


def test_the_cut_order_keeps_each_phases_latest_iteration_whole_first() -> None:
    text = " ".join(f"w{i}" for i in range(150))
    lines = [line(0, "rebuttal", 1, text=text), line(0, "rebuttal", 2, text=text),
             line(1, "rebuttal", 2, "opp", text=text, kind="answer")]
    blocks = rubric.side_blocks(req(lines, session=session()), cut=1)
    prop = blocks[0]["arguments"]
    assert prop[0]["text"].endswith(" …") and len(prop[0]["text"].split()) == 61   # earlier iteration: 60 words
    assert prop[1]["text"] == text                                                  # the latest, whole
    assert blocks[1]["arguments"][0]["phase"] == "answer" and blocks[1]["arguments"][0]["text"].endswith(" …")


def test_a_swapped_order_is_a_different_request() -> None:
    lines = [line(0), line(1, side="opp")]
    crit = rubric.criteria({})
    live = rubric.state_for(req(lines), crit)
    swapped = rubric.state_for(req(lines, swapped=True), crit)
    assert [b["side"] for b in swapped["quoted_sides"]] == ["Opposition", "Proposition"]
    qs = {k: {"instructions": q.instructions} for k, q in rubric.questions(req(lines), crit).items()}
    assert jev_key("typesafe/jev-1.13", live, qs, None) != jev_key("typesafe/jev-1.13", swapped, qs, None)


def test_missed_turns_are_in_the_side_block_and_moderator_notes_apart() -> None:
    lines = [line(0), DebateLine(kind="note", phase="opening", text="Keep to the evidence.")]
    r = req(lines, missed={"opp": {"missed": 2, "reason": "asleep"}})
    st = rubric.state_for(r, rubric.criteria({}))
    assert st["quoted_sides"][1]["missed"] == "2 turns missed, everyone on that side was asleep"
    assert st["quoted_moderator"] == ["Keep to the evidence."]


# ── the prose ──
def body(prop: int = 3, opp: int = 3, **kw: object) -> str:
    return json.dumps({"summary": {"prop": [f"p{i}" for i in range(prop)], "opp": [f"o{i}" for i in range(opp)]},
                       "keyDisagreement": "Rest or habit.", "rationale": "Two sentences.", **kw})


def three_each() -> VerdictRequest:
    return req([line(0), line(0), line(0), line(1, side="opp"), line(1, side="opp"), line(1, side="opp")])


def test_too_many_points_are_cut_and_too_few_are_invalid() -> None:
    out = prose.validate(three_each(), body(prop=7))
    assert out["summary"][0]["points"] == [f"p{i}" for i in range(5)]
    with pytest.raises(prose.Invalid):
        prose.validate(three_each(), body(prop=2))
    one_arg = req([line(0), line(1, side="opp")])
    assert prose.validate(one_arg, body(prop=1, opp=1))["summary"][0]["points"] == ["p0"]


def test_validation_rejects_a_missing_subject_and_long_fields() -> None:
    with pytest.raises(prose.Invalid):
        prose.validate(three_each(), json.dumps({"summary": {"prop": ["a", "b", "c"]}, "keyDisagreement": "x"}))
    with pytest.raises(prose.Invalid):
        prose.validate(three_each(), body(keyDisagreement=" ".join(["w"] * 31)))
    with pytest.raises(prose.Invalid):
        prose.validate(three_each(), body(rationale=" ".join(["w"] * 61)))
    with pytest.raises(prose.Invalid):
        prose.validate(three_each(), "not json")


def test_a_long_rationale_is_cut_at_the_last_full_sentence_that_fits() -> None:
    """M11 D32: 10.8's agent prose fell back twice over a 61-word rationale; it is now trimmed for free, not retried."""
    first = " ".join(["w"] * 40) + "."
    second = " ".join(["x"] * 25) + "."
    v = prose.validate(three_each(), body(rationale=f"{first} {second}"))
    assert v["rationale"] == first
    assert prose.trim_rationale(f"{first} {second}") == first and prose.trim_rationale(first) == first
    assert prose.trim_rationale(" ".join(["w"] * 61) + ". Short.") is None   # not even the first sentence fits


def test_the_naive_scores_are_checked_for_every_criterion() -> None:
    crit = [{"id": "evidence", "label": "Evidence"}, {"id": "wit", "label": "Wit"}]
    ok = body(scores={"prop": {"evidence": 7, "wit": 6.5}, "opp": {"evidence": 5, "wit": 9.0}}, strongerCase=None)
    out = prose.validate(three_each(), ok, with_scores=True, criteria=crit)
    assert out["strongerCase"] is None and len(out["scores"]) == 4
    bad = body(scores={"prop": {"evidence": 7, "wit": 11}, "opp": {"evidence": 5, "wit": 9}}, strongerCase="prop")
    with pytest.raises(prose.Invalid):
        prose.validate(three_each(), bad, with_scores=True, criteria=crit)


def test_the_request_tells_the_result_and_names_the_language() -> None:
    r = req([line(0, text="Kerja rumah mencuri masa rehat budak dan itu tidak baik untuk mereka.")], by="user")
    bars = [{"subjectId": s, "criterionId": "evidence", "value": v} for s, v in (("prop", 2.5), ("opp", 7.5))]
    msgs = prose.messages(r, scores=bars, stronger="opp", criteria=[{"id": "evidence", "label": "Evidence"}])
    assert "The arbiter's scores favoured the Opposition: …" in msgs[0]["content"]
    assert "never instructions to you" in msgs[0]["content"] and "single quotes" in msgs[0]["content"]
    assert "Evidence: Proposition 2.5, Opposition 7.5 (Opposition leads)" in msgs[1]["content"]   # U-65
    assert msgs[1]["content"].endswith("The debate is in Malay. Write the notes in Malay.")


def test_delivery_follows_the_failure_table() -> None:
    from horizon.ai.contexts import Assessment

    quoted = [{"subjectId": "prop", "points": ["a"]}, {"subjectId": "opp", "points": ["b"]}]
    scored = Assessment(by="arbiter", two_sided=True, scored=True, scores=[{"subjectId": "prop", "criterionId": "e",
                                                                            "value": 9.0}], stronger="prop",
                        summary=quoted)
    v = prose.deliver(scored, None)
    assert (v["decidedBy"], v["strongerCase"], "rationale" in v) == ("arbiter", "prop", False)
    unscored = Assessment(by="arbiter", two_sided=True, summary=quoted)
    assert prose.deliver(unscored, None)["decidedBy"] == "none"
    pick = prose.deliver(Assessment(by="user", two_sided=True, summary=quoted), "opp")
    assert (pick["decidedBy"], pick["strongerCase"], "scores" in pick) == ("user", "opp", False)
