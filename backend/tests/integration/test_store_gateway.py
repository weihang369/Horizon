"""The response store inside the gateway (response-store spec; docs/ai/13 W10; ai-foundation design D31; tasks 7.1,
7.2). Test mode never attaches a store unless the test passes a temp one."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from horizon.evals.store import ResponseStore
from horizon.gateway.context import call_ctx
from tests.conftest import Api
from tests.knowledge.kit import add_text, settle, source

API = "/api/v1"
SEED_SRC = "kno_seedAmara1"
STATE = {"quoted_message": "hi"}
QUESTIONS = {"q": {"type": "noul", "instructions": "x?", "criteria": {"true": "yes", "false": "no"}}}


async def ledger_count(api: Api, where: str) -> int:
    async with api.rt.db.read() as conn:
        return int((await conn.execute(text(f"SELECT COUNT(*) FROM usage_records WHERE is_seed = 0 AND {where}")))
                   .scalar_one())


async def test_test_mode_attaches_no_store(api: Api) -> None:
    assert api.rt.gateway.store is None and api.rt.gateway.seed_store is None


async def test_a_jev_hit_sends_nothing_and_writes_no_row(api: Api, tmp_path: Path) -> None:
    await api.set_key()
    gw = api.rt.gateway
    gw.store = ResponseStore.eval_view(tmp_path, None)
    fake = api.rt.fake
    assert fake is not None
    first = await gw.decide(STATE, QUESTIONS, call_ctx("eval_judge"))
    sent = fake.counts["decisions"]
    rows = await ledger_count(api, "purpose = 'eval_judge'")
    again = await gw.decide(STATE, QUESTIONS, call_ctx("eval_judge"))
    assert again.answers == first.answers and again.generation_id == "store"
    assert fake.counts["decisions"] == sent == 1 and await ledger_count(api, "purpose = 'eval_judge'") == rows == 1
    gw.store = ResponseStore.eval_view(tmp_path, "f" * 64)                 # another canary baseline: a miss
    await gw.decide(STATE, QUESTIONS, call_ctx("eval_judge"))
    assert fake.counts["decisions"] == 2


def entries(root: Path) -> int:
    return len(list(root.glob("*.json")))


async def test_the_reversed_ask_is_sent_and_stored_apart(api: Api, tmp_path: Path) -> None:
    """M15 (images-music D13): the decisions suite's reversed-option ask reaches Jev once and is kept under its own key;
    the declared-order ask still hits its old entry."""
    await api.set_key()
    gw = api.rt.gateway
    gw.store = ResponseStore.eval_view(tmp_path, None)
    fake = api.rt.fake
    assert fake is not None
    q = {"q": {"type": "choice", "instructions": "x?", "criteria": {"a": "A", "b": "B"}}}
    rev = {"q": {"type": "choice", "instructions": "x?", "criteria": {"b": "B", "a": "A"}}}
    first = await gw.decide(STATE, q, call_ctx("eval_judge"))
    second = await gw.decide(STATE, rev, call_ctx("eval_judge"), order={"q": ["b", "a"]})
    assert fake.counts["decisions"] == 2 and entries(tmp_path) == 2
    # the fake picks the first option, so a reversed ask that really reached it shows as a flip (M9 saw 0 of 100)
    assert first.answers["q"]["choice"] == "a" and second.answers["q"]["choice"] == "b"
    await gw.decide(STATE, q, call_ctx("eval_judge"))
    await gw.decide(STATE, rev, call_ctx("eval_judge"), order={"q": ["b", "a"]})
    assert fake.counts["decisions"] == 2                                   # both now served from the store


async def test_seed_view_reuses_seed_embeddings_and_never_keeps_user_text(api: Api, tmp_path: Path) -> None:
    store_dir = tmp_path / "cache"
    api.rt.gateway.seed_store = ResponseStore.seed_view(store_dir)
    await api.set_key()
    r = await api.post(f"{API}/_test/ai-profile", {"profile": "scripted", "overrides": {"embedder": "naive"}})
    assert r.status_code == 204
    fake = api.rt.fake
    assert fake is not None
    assert (await api.client.post(f"{API}/knowledge/{SEED_SRC}/reindex")).status_code == 200
    await settle(api)
    assert (await source(api, SEED_SRC))["source"]["status"] == "indexed"
    sent, rows = fake.counts["embeddings"], await ledger_count(api, "category = 'embedding'")
    stored = len(list(store_dir.glob("*.json")))
    assert sent > 0 and rows > 0 and stored == sent
    assert (await api.post(f"{API}/admin/reset-demo", {"confirm": True})).status_code == 204
    api.rt.gateway.seed_store = ResponseStore.seed_view(store_dir)        # what a normal start attaches
    assert (await api.client.post(f"{API}/knowledge/{SEED_SRC}/reindex")).status_code == 200
    await settle(api)
    assert (await source(api, SEED_SRC))["source"]["status"] == "indexed"
    assert fake.counts["embeddings"] == sent                               # nothing sent the second time
    assert await ledger_count(api, "category = 'embedding'") == rows       # and no row: nothing was spent
    user = await add_text(api, "Tea", "Steep the green tea for three minutes.")
    await settle(api)
    assert (await source(api, user["id"]))["source"]["status"] == "indexed"
    assert fake.counts["embeddings"] > sent                                # user text is always sent…
    assert len(list(store_dir.glob("*.json"))) == stored                    # …and never stored


async def test_a_streamed_store_hit_is_captured_with_its_text(api: Api, tmp_path: Path) -> None:
    """M15 8.9: a replayed reply reaches the capture hook like a live one, so `conversations` reads naive's raw text
    (the note-in-tag rate, D14) on a run served from the store."""
    from horizon.gateway.chat import ChatRequest

    await api.set_key()
    gw = api.rt.gateway
    gw.store = ResponseStore.eval_view(tmp_path, None)
    seen: list[tuple[dict, dict]] = []
    gw.capture_bodies, gw.on_call = True, lambda ctx, summary, outcome: seen.append((summary, outcome))
    req = ChatRequest(model="deepseek/deepseek-v4.1-flash", messages=[{"role": "user", "content": "hi"}], max_tokens=16)
    live = "".join([c.content async for c in gw.chat_stream(req, call_ctx("reply", category="chat"))
                    if c.content])
    seen.clear()
    replayed = "".join([c.content async for c in gw.chat_stream(req, call_ctx("reply", category="chat"))
                        if c.content])
    assert replayed == live != ""
    assert [(s["body"]["response"]["text"], o["provider"]) for s, o in seen] == [(live, "store")]
