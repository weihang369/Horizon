"""The Jev request manifest (images-music design D19; evaluation-harness "The Jev request manifest"). Built from the
datasets at $0; a comparison run refuses any Jev body it doesn't list. No network."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from horizon.evals.manifest import body_hash, build, decisions_bodies
from horizon.evals.runner import EVALS_DIR
from horizon.evals.store import ResponseStore, jev_key
from horizon.gateway.context import call_ctx
from horizon.gateway.errors import ProviderError
from tests.conftest import SEED_DIR, Api

JEV = json.loads((SEED_DIR / "pricing.json").read_text(encoding="utf-8"))["data"]["decision"]["model"]
FP = json.loads((EVALS_DIR / "canary.json").read_text(encoding="utf-8"))["fingerprint"]


def test_every_set_is_listed_by_hash_only(tmp_path: Path) -> None:
    doc = build(model=JEV, fingerprint=FP, store_root=tmp_path / "cache", private_store_root=tmp_path / "private",
                test_mode=True)
    sets = doc["sets"]
    assert {"canary", "deep-check", "judges", "emotion"} <= set(sets)
    assert sets["canary"]["n"] == 20 and sets["canary"]["stored"] == 0
    assert any(k.startswith("safety:") for k in sets)                     # the committed harmless items in test mode
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for s in sets.values() for h in s["bodies"])
    assert doc["model"] == JEV and doc["fingerprint"] == FP and doc["bank"]["emotion_reply"] >= 1
    text = json.dumps(doc)
    _name, state, _qs, _order = next(iter(decisions_bodies()))
    assert all(str(v) not in text for v in state.values() if isinstance(v, str) and len(v) > 12)   # no item text


def test_a_stored_answer_is_counted(tmp_path: Path) -> None:
    name, state, qs, order = next(iter(decisions_bodies()))
    store = ResponseStore.eval_view(tmp_path / "cache", FP)
    assert store.put("jev", jev_key(JEV, state, qs, FP, order), {"state": state, "questions": qs}, {"answers": {}}, None)
    doc = build(model=JEV, fingerprint=FP, store_root=tmp_path / "cache", private_store_root=tmp_path / "private",
                test_mode=True)
    assert doc["sets"][name]["stored"] == 1
    assert body_hash(state, qs) in doc["sets"][name]["bodies"]


async def test_a_comparison_refuses_an_unlisted_body_and_names_it(api: Api) -> None:
    await api.set_key()
    state = {"quoted_message": "hi"}
    listed = {"q": {"type": "noul", "instructions": "listed?", "criteria": {"true": "yes", "false": "no"}}}
    other = {"other_q": {"type": "noul", "instructions": "changed?", "criteria": {"true": "yes", "false": "no"}}}
    api.rt.gateway.allowed_bodies = frozenset({body_hash(state, listed)})
    fake = api.rt.fake
    assert fake is not None
    await api.rt.gateway.decide(state, listed, call_ctx("eval_judge"))
    sent = fake.counts["decisions"]
    with pytest.raises(ProviderError) as e:
        await api.rt.gateway.decide(state, other, call_ctx("eval_judge"))
    assert "other_q" in e.value.message and fake.counts["decisions"] == sent == 1
