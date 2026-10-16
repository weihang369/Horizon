"""Message vectors in an embedding-space build (memory design D6, tasks 1.4, 1.5; embedding-spaces "Dropped lines have
vectors in the space").

The indexed lines recall searches are copied when the model and dimensions don't change and embedded again when they
do, plain (no header), partitioned by session, and never through the response store: they are the user's text (W10).
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlite_vec
from sqlalchemy import text

from horizon.ai.embedder import PieceMeta, request_text
from horizon.db import spaces
from horizon.db.spaces import DEFAULT_SPACE, PLAIN_SPACE, SpaceSpec
from horizon.services.knowledge.build import build_space, plan_build
from tests.conftest import Api

HASH64 = SpaceSpec(id="hash@64", model=DEFAULT_SPACE.model, provider="test", dims=64,
                   query_instruction=DEFAULT_SPACE.query_instruction)


async def indexed_lines(api: Api, n: int) -> tuple[str, list[str]]:
    """Index the first `n` messages of a seed session as dropped lines, with a vector each in the active space."""
    space = api.rt.space_id or ""
    table = spaces.message_vec_table(space)
    async with api.rt.db.write() as tx:
        c = tx.conn
        sid = (await c.execute(text("SELECT session_id FROM messages GROUP BY session_id "
                                    "HAVING count(*) >= :n ORDER BY session_id LIMIT 1"), {"n": n})).scalar_one()
        rows = (await c.execute(text("SELECT id, seq, content FROM messages WHERE session_id = :s ORDER BY seq LIMIT :n"),
                                {"s": sid, "n": n})).all()
        texts = []
        for mid, seq, content in rows:
            line = f"Kai: {content or 'hello'}"
            texts.append(line)
            rid = (await c.execute(text(
                "INSERT INTO message_index(message_id, session_id, seq, author, text, created_at) "
                "VALUES (:m, :s, :q, 'Kai', :t, '2026-10-16T03:00:00.000Z') RETURNING rid"),
                {"m": mid, "s": sid, "q": seq, "t": line})).scalar_one()
            await c.execute(text(f"INSERT INTO {table}(rid, session_id, embedding) VALUES (:r, :s, :e)"),
                            {"r": rid, "s": sid, "e": sqlite_vec.serialize_float32([0.5] * 1024)})
    return str(sid), texts


async def line_vectors(api: Api, space_id: str, sid: str) -> int:
    async with api.rt.db.read() as conn:
        return int((await conn.execute(text(f"SELECT count(*) FROM {spaces.message_vec_table(space_id)} "
                                            f"WHERE session_id = :s"), {"s": sid})).scalar_one())


def test_a_line_is_sent_plain_even_in_the_header_space() -> None:
    """Task 1.5: the `message` kind has no header and no instruction, whatever the space's template."""
    line = "Kai: my sister Mia just started nights in Ipoh."
    assert request_text(line, "message", DEFAULT_SPACE) == line
    assert request_text(line, "message", DEFAULT_SPACE, PieceMeta("Notes.md", "Mia", None)) == line


async def test_same_model_and_dims_copies_the_line_vectors(api: Api) -> None:
    await api.set_key()
    sid, _ = await indexed_lines(api, 6)
    plan = await plan_build(api.rt, PLAIN_SPACE)
    assert (plan.messages, plan.copy_messages) == (0, 6)
    sent = len([r for r in api.rt.fake.requests if r.url.path.endswith("/embeddings")]) if api.rt.fake else 0
    report = await build_space(api.rt, PLAIN_SPACE)
    assert (report.copied_messages, report.messages) == (6, 0)
    assert await line_vectors(api, PLAIN_SPACE.id, sid) == 6
    assert api.rt.fake is not None
    assert len([r for r in api.rt.fake.requests if r.url.path.endswith("/embeddings")]) == sent   # copied: no request


async def test_new_dims_embed_the_lines_again_plain_and_never_stored(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    await api.set_key()
    sid, texts = await indexed_lines(api, 4)
    plan = await plan_build(api.rt, HASH64)
    assert (plan.messages, plan.copy_messages) == (4, 0)
    assert plan.tokens >= sum(len(t) for t in texts) // 4   # the lines are counted in the estimate
    embedder = api.rt.ai.embedder(True)
    seen: list[tuple[str, list[str], bool, str | None]] = []
    real = embedder.embed

    async def spy(texts_: Any, *, kind: str, space: Any, ctx: Any, hooks: Any = None, meta: Any = None) -> Any:
        h = hooks(None) if callable(hooks) else hooks
        seen.append((kind, list(texts_), bool(getattr(h, "store_ok", False)), ctx.session_id))
        return await real(texts_, kind=kind, space=space, ctx=ctx, hooks=hooks, meta=meta)

    monkeypatch.setattr(embedder, "embed", spy)
    report = await build_space(api.rt, HASH64)
    assert report.messages == 4 and report.copied_messages == 0
    lines = [s for s in seen if s[0] == "message"]
    assert lines and all(not store_ok and session == sid for _, _, store_ok, session in lines)
    assert sorted(t for _, batch, _, _ in lines for t in batch) == sorted(texts)
    assert await line_vectors(api, HASH64.id, sid) == 4


async def test_unknown_kind_is_refused(api: Api) -> None:
    await api.set_key()
    with pytest.raises(ValueError):
        await build_space(api.rt, PLAIN_SPACE, kinds=("lines",))
