"""The retrieval gates in every plan (docs/ai/01 A4; doc 10 K4; doc 13 W1, W5 rows 2, 5, 6; rag design D6–D8, D20).

Each plan's one Jev request also asks:
- **"needs documents?"** (`docs:{characterId}`) about each candidate with a searchable source (`indexed` or
  `keyword_only`) whose gate wasn't dropped by X9's cap;
- **"standalone?" and "English?"** once about the message, in 1:1 and when a group message is answered, only when some
  "needs documents?" is asked (A4: only when it can pay off). Debate and watch never rewrite, so never ask them.

Only the speaker's own answer counts: at or above `t_gate` the reply goes deep. A late, failed or refused answer, or a
dropped gate, is quick (A4: a gate fallback is quick). Abstaining (the not-found line) is allowed only for a reply to a
user message in 1:1 or group, at or above `t_confident` (D8). The System 1 rows (D20) are built here so every plan
writes them the same way.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from horizon.ai.agent.persona import first_name
from horizon.ai.contexts import GateAnswer, MessageNouls
from horizon.ai.decider import Answers, DecisionResult, NoulAnswer, Question
from horizon.ai.questions import bank

GATE = "docs"
EARLIER = "earlier"   # M13 (memory D26): "needs something from earlier?", per candidate with something to search
STANDALONE = "standalone"
ENGLISH = "english"
# D8: the kinds whose reply answers a user message in 1:1 or group, so may abstain (the second reply is the follow plan)
ABSTAIN_KINDS: frozenset[str] = frozenset({"reply", "group_first", "group_mentioned", "everyone", "second"})
# D8: the cast plan kinds that ask "standalone?" and "English?" (a group message being answered)
NOUL_KINDS: frozenset[str] = frozenset({"group_first", "group_mentioned", "everyone"})


NAME_MAX = 40


def _name(full: str) -> str:
    """As the turn plan names a subject: the full name, or the first name over the label limit."""
    return full if len(full) <= NAME_MAX else first_name(full)[:NAME_MAX]


def plan_wait(deps: Any, base_s: float, gated: bool) -> float:
    """U-46: how long a plan is waited for, in seconds: to the end when it asks "needs documents?" about someone (deep
    insight waits for every stage, D-111), else `base_s`. A profile without agent knobs keeps `base_s`."""
    if not gated:
        return base_s
    get = getattr(deps, "retrieval", None)
    r = get() if get is not None else None
    agent = r.agent if r is not None else None
    return float(agent.plan_wait_s(base_s, gated)) if agent is not None else base_s


SKIP_NO_DOCS = "skipped: no searchable documents"
SKIP_NOTHING_EARLIER = "skipped: nothing earlier to search"
SKIP_TOO_LARGE = "skipped: the plan's state was too large"


def skipped_row(qid: str, *, purpose: str, reason: str, about: str | None = None) -> dict[str, Any]:
    """U-49 (the maintainer's choice): a question this turn didn't ask, greyed in Insight with its reason, so every turn of a
    mode lists the same rows."""
    e = bank().get(qid)
    row: dict[str, Any] = {"purpose": purpose, "id": qid, "version": e.version, "label": e.label}
    if about is not None:
        row["about"] = about
    row.update(answer="\u2014", compared=[], result="skipped", action=reason)
    return row


def gate_key(cid: str) -> str:
    return f"{GATE}:{cid}"


def earlier_key(cid: str) -> str:
    return f"{EARLIER}:{cid}"


def t_earlier() -> float:
    return float(bank().get(EARLIER).thresholds.get("t_gate", 0.4))


def recall_asked(candidates: Sequence[str], recallable: Sequence[str], dropped: Sequence[str] = ()) -> list[str]:
    """M13 (D26): who is asked "needs something from earlier?": candidates with something to search (the session has
    indexed lines, or the candidate has an overflow) whose gates X9's cap didn't drop."""
    have = set(recallable)
    return [c for c in candidates if c in have and c not in dropped]


def thresholds() -> dict[str, float]:
    b = bank()
    d, s, e = b.get(GATE).thresholds, b.get(STANDALONE).thresholds, b.get(ENGLISH).thresholds
    return {"t_gate": float(d.get("t_gate", 0.35)), "t_confident": float(d.get("t_confident", 0.8)),
            "t_standalone": float(s.get("t_standalone", 0.5)), "english": float(e.get("english", 0.5))}


def gated(candidates: Sequence[str], documents: Mapping[str, Sequence[str]], dropped: Sequence[str] = ()) -> list[str]:
    """Who is asked "needs documents?": candidates with searchable sources whose gate X9's cap didn't drop."""
    return [c for c in candidates if documents.get(c) and c not in dropped]


def questions(names: Mapping[str, str], who: Sequence[str], *, nouls: bool,
              recall: Sequence[str] = ()) -> dict[str, Question]:
    """The gate questions to add to a plan's request. M13 (D26): `recall` are asked "needs something from earlier?"."""
    b = bank()
    qs: dict[str, Question] = {gate_key(c): b.question(GATE, name=_name(names.get(c, c)), about=c) for c in who}
    if nouls and who:
        qs[STANDALONE] = b.question(STANDALONE)
        qs[ENGLISH] = b.question(ENGLISH)
    for c in recall:
        qs[earlier_key(c)] = b.question(EARLIER, name=_name(names.get(c, c)), about=c)
    return qs


def fallbacks(qs: Mapping[str, Question]) -> Answers:
    """Every gate's fallback: no (quick, no rewrite). The Decider marks them `source="fallback"`."""
    return {k: NoulAnswer(0.0) for k in qs
            if k.startswith((f"{GATE}:", f"{EARLIER}:")) or k in (STANDALONE, ENGLISH)}


def _p(res: DecisionResult, key: str) -> float | None:
    a = res.answers.get(key)
    return a.p if isinstance(a, NoulAnswer) and a.source != "fallback" else None


def read(res: DecisionResult, who: Sequence[str], *, nouls: bool,
         message_id: str | None = None) -> tuple[dict[str, GateAnswer], MessageNouls | None]:
    """The answers, as code sees them: p, or None and why."""
    why = "late" if res.failure == "timeout" else "fallback"
    gates: dict[str, GateAnswer] = {}
    for c in who:
        p = _p(res, gate_key(c))
        gates[c] = GateAnswer(p=p, outcome="jev" if p is not None else why)   # type: ignore[arg-type]
    msg: MessageNouls | None = None
    if nouls and who:
        s, e = _p(res, STANDALONE), _p(res, ENGLISH)
        msg = MessageNouls(standalone=s, english=e, outcome="jev" if s is not None and e is not None else why,  # type: ignore[arg-type]
                           message_id=message_id)
    return gates, msg


def read_recall(res: DecisionResult, who: Sequence[str]) -> dict[str, GateAnswer]:
    """M13 (D26): the "needs something from earlier?" answers, as code sees them."""
    why = "late" if res.failure == "timeout" else "fallback"
    out: dict[str, GateAnswer] = {}
    for c in who:
        p = _p(res, earlier_key(c))
        out[c] = GateAnswer(p=p, outcome="jev" if p is not None else why)   # type: ignore[arg-type]
    return out


def recalls(gate: GateAnswer | None) -> bool:
    """M13 (D26): recall runs for the speaker at or above its own `t_gate`; late, failed or dropped: no recall."""
    return gate is not None and gate.p is not None and gate.p >= t_earlier()


def branch(gate: GateAnswer | None, recall_gate: GateAnswer | None = None) -> Literal["quick", "deep"]:
    """A turn is deep when "needs documents?" or "needs something from earlier?" says yes for its speaker."""
    return "deep" if deep(gate) or recalls(recall_gate) else "quick"


def recall_row(cid: str, gate: GateAnswer, *, purpose: str, result: str | None = None) -> dict[str, Any]:
    """M13 (D35): one "needs something from earlier?" row about a candidate, as the `docs` rows are built."""
    e = bank().get(EARLIER)
    row: dict[str, Any] = {"purpose": purpose, "id": EARLIER, "version": e.version, "label": e.label, "about": cid}
    if gate.p is None:
        row.update(answer="no", compared=[], result="fallback" if result != "not_used" else "not_used",
                   action="no recall")
        return row
    p = round(gate.p, 4)
    yes = gate.p >= t_earlier()
    row.update(answer="yes" if yes else "no", p=p, compared=[{"name": "t_gate", "value": p,
                                                               "threshold": t_earlier()}],
               result=result or "used", action="search earlier lines" if yes else "no recall")
    return row


def dropped(who: Sequence[str]) -> dict[str, GateAnswer]:
    """X9's cap dropped these candidates' gates: no question, a quick turn."""
    return {c: GateAnswer(p=None, outcome="dropped") for c in who}


def deep(gate: GateAnswer | None) -> bool:
    return gate is not None and gate.p is not None and gate.p >= thresholds()["t_gate"]


def abstain_allowed(gate: GateAnswer | None, kind: str) -> bool:
    """D8: a reply to a user message in 1:1 or group, confident that documents are needed."""
    return kind in ABSTAIN_KINDS and gate is not None and gate.p is not None and gate.p >= thresholds()["t_confident"]


def gate_row(cid: str, gate: GateAnswer, *, purpose: str, abstain_kind: bool, result: str | None = None) -> dict[str, Any]:
    """D20's "needs documents?" row about one candidate. `result`: `used` (the speaker's), `not_used` (the others')."""
    e = bank().get(GATE)
    th = thresholds()
    row: dict[str, Any] = {"purpose": purpose, "id": GATE, "version": e.version, "label": e.label, "about": cid}
    if gate.p is None:
        row.update(answer="no", compared=[], result="fallback" if result != "not_used" else "not_used",
                   action="quick reply")
        return row
    p = round(gate.p, 4)
    compared = [{"name": "t_gate", "value": p, "threshold": th["t_gate"]}]
    if abstain_kind:
        compared.append({"name": "t_confident", "value": p, "threshold": th["t_confident"]})
    yes = gate.p >= th["t_gate"]
    row.update(answer="yes" if yes else "no", p=p, compared=compared, result=result or "used",
               action="search the documents" if yes else "quick reply")
    return row


def noul_rows(msg: MessageNouls, *, purpose: str, considered: bool) -> list[dict[str, Any]]:
    """D20's "standalone?" and "English?" rows: `used` when a rewrite was considered (the turn went deep)."""
    th = thresholds()
    out: list[dict[str, Any]] = []
    for qid, p, name in ((STANDALONE, msg.standalone, "t_standalone"), (ENGLISH, msg.english, "english")):
        e = bank().get(qid)
        row: dict[str, Any] = {"purpose": purpose, "id": qid, "version": e.version, "label": e.label}
        if p is None:
            row.update(answer="no", compared=[], result="fallback", action="no rewrite")
        else:
            yes = p >= th[name]
            row.update(answer="yes" if yes else "no", p=round(p, 4),
                       compared=[{"name": name, "value": round(p, 4), "threshold": th[name]}],
                       result="used" if considered else "not_used",
                       action="no rewrite needed" if yes else "rewrite the query")
        out.append(row)
    return out


def speaker_rows(cid: str, gates: Mapping[str, GateAnswer], msg: MessageNouls | None, *, purpose: str, kind: str,
                 everyone: bool = False, recall_gates: Mapping[str, GateAnswer] | None = None,
                 skips: bool = True) -> list[dict[str, Any]]:
    """A reply's gate rows: its own `docs` row, the other candidates' `not_used` (none on an Everyone reply, D22), and
    the message's nouls when asked. U-49 (`skips`): the speaker's own gate that wasn't asked is a `skipped` row with
    its reason (no searchable documents, nothing earlier to search, or X9's cap)."""
    rows: list[dict[str, Any]] = []
    abstain_kind = kind in ABSTAIN_KINDS
    own = gates.get(cid)
    if skips and (own is None or own.outcome == "dropped"):
        rows.append(skipped_row(GATE, purpose=purpose, about=cid,
                                reason=SKIP_TOO_LARGE if own is not None else SKIP_NO_DOCS))
    for other, g in gates.items():
        if g.outcome == "dropped":
            continue
        if other == cid:
            rows.append(gate_row(other, g, purpose=purpose, abstain_kind=abstain_kind))
        elif not everyone:
            rows.append(gate_row(other, g, purpose=purpose, abstain_kind=abstain_kind, result="not_used"))
    if msg is not None:
        rows.extend(noul_rows(msg, purpose=purpose, considered=deep(gates.get(cid))))
    mine = (recall_gates or {}).get(cid)
    if skips and (mine is None or mine.outcome == "dropped"):
        rows.append(skipped_row(EARLIER, purpose=purpose, about=cid,
                                reason=SKIP_TOO_LARGE if mine is not None else SKIP_NOTHING_EARLIER))
    for other, g in (recall_gates or {}).items():   # M13 (D35): the earlier rows, after the docs rows
        if g.outcome == "dropped":
            continue
        if other == cid:
            rows.append(recall_row(other, g, purpose=purpose))
        elif not everyone:
            rows.append(recall_row(other, g, purpose=purpose, result="not_used"))
    return rows
