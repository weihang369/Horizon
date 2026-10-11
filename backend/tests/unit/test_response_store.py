"""The response store's key rule and file format (docs/ai/13 W10; response-store spec; design D31; task 7.1). The two
fixtures are group A entries copied from `data/cache/`: one keyed without a fingerprint, one with the canary's."""

from __future__ import annotations

import json
from pathlib import Path

from horizon.evals.store import ResponseStore, chat_key, jev_key
from tests.conftest import SEED_DIR

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "store"
REPO = Path(__file__).resolve().parents[3]
JEV = json.loads((SEED_DIR / "pricing.json").read_text(encoding="utf-8"))["data"]["decision"]["model"]
FINGERPRINT = json.loads((REPO / "docs/ai/checks/group-a/results/canary.json").read_text(encoding="utf-8"))["fingerprint"]


def entry(name: str) -> dict[str, object]:
    out: dict[str, object] = json.loads((FIX / name).read_text(encoding="utf-8"))
    return out


def test_group_a_jev_key_without_a_fingerprint() -> None:
    name = "1e990cbfc962fa9bc24b6cd6c85ea60596508f386da7f79e8e86314f1cc4e99b.json"
    req = entry(name)["request"]
    assert isinstance(req, dict)
    assert jev_key(JEV, req["state"], req["questions"], None) + ".json" == name


def test_group_a_jev_key_with_the_canary_fingerprint() -> None:
    name = "03f58c0f98e05d2c116783f47f90a7d4a5b921712609641d2bb7fa6586f2c089.json"
    req = entry(name)["request"]
    assert isinstance(req, dict)
    assert jev_key(JEV, req["state"], req["questions"], FINGERPRINT) + ".json" == name
    assert jev_key(JEV, req["state"], req["questions"], "0" * 64) + ".json" != name   # another baseline misses


def test_chat_key_ignores_stream_and_routing_order() -> None:
    body = {"model": "m", "provider": {"order": ["DeepSeek"]}, "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 10, "stream": True}
    assert chat_key(body) == chat_key({**body, "stream": False})
    assert chat_key(body) != chat_key({**body, "max_tokens": 11})


def test_first_write_wins_and_views(tmp_path: Path) -> None:
    s = ResponseStore.eval_view(tmp_path, None)
    assert s.put("jev", "k1", {"a": 1}, {"answers": 1}, {"cost": 0.1}) is True
    assert s.put("jev", "k1", {"a": 2}, {"answers": 2}, {}) is False
    got = s.get("jev", "k1")
    assert got is not None and got["response"] == {"answers": 1} and set(got) == {"request", "response", "usage", "savedAt"}
    assert list(tmp_path.glob("*.tmp")) == []
    seed = ResponseStore.seed_view(tmp_path)
    assert seed.get("jev", "k1") is None and seed.put("chat", "k2", {}, {}, {}) is False   # seed view: embeddings only
    assert seed.put("embeddings", "k3", {"input": ["x"]}, {"data": []}, {}) is True
