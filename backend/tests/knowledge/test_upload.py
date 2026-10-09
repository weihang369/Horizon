"""The knowledge upload route (knowledge-memory-storage task 3.2; http-api "Knowledge and memory write routes",
"Knowledge upload limit is enforced while reading"; knowledge-sources "Accepted inputs", "Knowledge limits")."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from sqlalchemy import text

from tests import docs_kit
from tests.conftest import Api

API = "/api/v1"
HANA = "chr_seedHana"
BOUNDARY = "----horizonboundary"


async def add_file(api: Api, name: str, data: bytes, mime: str = "", **kw: Any) -> Any:
    files = {"file": (name, data, mime)} if mime else {"file": (name, data)}
    return await api.client.post(f"{API}/characters/{HANA}/knowledge", files=files, **kw)


async def add_text(api: Api, title: str, body: str, character: str = HANA) -> Any:
    return await api.client.post(f"{API}/characters/{character}/knowledge", json={"type": "text", "title": title, "text": body})


async def sources(api: Api) -> list[dict[str, Any]]:
    return list((await api.client.get(f"{API}/characters/{HANA}/knowledge")).json())


def leftovers(api: Api) -> list[Path]:
    tmp = list(api.rt.cfg.tmp_dir.glob("*")) if api.rt.cfg.tmp_dir.exists() else []
    return tmp


def knowledge_files(api: Api) -> list[Path]:
    root = api.rt.cfg.knowledge_dir
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


async def test_pasted_text_is_201_and_contract_valid(api: Api) -> None:
    r = await add_text(api, "Notes", "Rice first.")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["type"] == "text" and body["status"] == "indexing" and body["title"] == "Notes"
    assert body["id"].startswith("kno_") and body["characterId"] == HANA and body["worldId"] == "wld_seedSunnyHollow"
    api.rt.schema.check("KnowledgeSource", body)
    assert api.rt.ingest.submitted == [body["id"]]
    [orig] = knowledge_files(api)
    assert orig.name == "original.txt" and orig.read_bytes() == b"Rice first."


async def test_markdown_file_is_accepted(api: Api) -> None:
    r = await add_file(api, "soups.md", b"# Soups\n\nMiso first.", "text/markdown")
    assert r.status_code == 201, r.text
    assert r.json()["type"] == "file" and r.json()["title"] == "soups.md"
    async with api.rt.db.read() as conn:
        row = (await conn.execute(text("SELECT * FROM knowledge_sources WHERE id = :i"), {"i": r.json()["id"]})).mappings().one()
    assert row["status"] == "queued" and row["has_original"] and row["original_name"] == "soups.md"
    assert row["sha256"] and row["mime"] == "text/markdown" and row["bytes"] == 20
    assert leftovers(api) == []


async def test_unsupported_content_type_is_422(api: Api) -> None:
    r = await api.client.post(f"{API}/characters/{HANA}/knowledge", content=b"hello", headers={"content-type": "text/plain"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation"
    assert await sources(api) == [s for s in await sources(api) if s["id"].startswith("kno_seed")]


async def test_rejections_create_nothing(api: Api) -> None:
    before = await sources(api)
    cases = [("sheet.csv", b"a,b\n1,2\n", "text/csv"), ("notes.html", b"%PDF-1.7", "text/html"),
             ("fake.pdf", b"not a pdf", "application/pdf"), ("report.docx", docs_kit.xlsx(), ""),
             ("notes.txt", b"\xff\xfe\x00h", "text/plain")]
    for name, data, mime in cases:
        r = await add_file(api, name, data, mime)
        assert r.status_code == 422, (name, r.text)
        assert r.json()["error"]["code"] == "validation"
    r = await add_text(api, "Long", "a" * (210 * 1024))
    assert r.status_code == 422 and r.json()["error"]["details"]["limit"] == 204800
    assert await sources(api) == before
    assert leftovers(api) == [] and knowledge_files(api) == []
    assert api.rt.ingest.submitted == []


async def test_unknown_or_tombstoned_character_is_404(api: Api) -> None:
    assert (await add_text(api, "x", "y", character="chr_nope")).status_code == 404
    assert (await api.client.delete(f"{API}/characters/chr_seedVictor")).status_code == 204
    assert (await add_text(api, "x", "y", character="chr_seedVictor")).status_code == 404


async def test_twenty_first_source_and_duplicates(api: Api) -> None:
    once = await add_file(api, "same.md", b"Same words twice.", "text/markdown")
    assert once.status_code == 201
    dup = await add_file(api, "copy.md", b"Same words twice.", "text/markdown")
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "conflict"
    assert dup.json()["error"]["details"]["existingSourceId"] == once.json()["id"]
    n = len(await sources(api))
    for i in range(n, 20):
        assert (await add_text(api, f"Note {i}", f"Recipe card number {i}.")).status_code == 201
    r = await add_text(api, "One more", "Overflow.")
    assert r.status_code == 422 and r.json()["error"]["details"]["limit"] == 20
    assert len(await sources(api)) == 20 and leftovers(api) == []


def multipart(name: str, payload: bytes) -> bytes:
    head = (f"--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
            f"Content-Type: text/plain\r\n\r\n").encode()
    return head + payload + f"\r\n--{BOUNDARY}--\r\n".encode()


async def test_chunked_oversize_upload_is_413(api: Api) -> None:
    body = multipart("huge.txt", b"a" * (11 * 1024 * 1024))

    async def chunks() -> AsyncIterator[bytes]:
        for i in range(0, len(body), 1 << 20):
            yield body[i:i + (1 << 20)]

    r = await api.client.post(f"{API}/characters/{HANA}/knowledge", content=chunks(),
                              headers={"content-type": f"multipart/form-data; boundary={BOUNDARY}"})
    assert r.status_code == 413, r.text
    assert r.json()["error"]["code"] == "validation" and r.json()["error"]["details"]["limit"] == 10485760
    assert leftovers(api) == [] and knowledge_files(api) == []


async def test_keyed_oversize_upload_is_413(api: Api) -> None:
    body = multipart("huge.txt", b"a" * (11 * 1024 * 1024))
    r = await api.client.post(f"{API}/characters/{HANA}/knowledge", content=body,
                              headers={"content-type": f"multipart/form-data; boundary={BOUNDARY}",
                                       "idempotency-key": "k-oversize-1"})
    assert r.status_code == 413, r.text
    assert r.json()["error"]["details"]["limit"] == 10485760
    assert knowledge_files(api) == []


async def test_exactly_ten_megabytes_is_accepted(api: Api) -> None:
    r = await add_file(api, "big.txt", b"a" * (10 * 1024 * 1024), "text/plain")
    assert r.status_code == 201, r.text[:200]


def drain(sub: Any) -> list[dict[str, Any]]:
    out = []
    while not sub.queue.empty():
        out.append(sub.queue.get_nowait())
    return out


async def test_created_source_is_announced_and_rejections_are_silent(api: Api) -> None:
    sub = api.rt.bus.subscribe("global")
    r = await add_file(api, "fake.pdf", b"not a pdf", "application/pdf")
    assert r.status_code == 422
    assert [e for e in drain(sub) if e.get("kind") == "knowledge"] == []
    r = await add_text(api, "Tea", "Steep for three minutes.")
    got = [e for e in drain(sub) if e.get("kind") == "knowledge"]
    assert got == [{"type": "entity.changed", "kind": "knowledge", "id": r.json()["id"], "worldId": "wld_seedSunnyHollow"}]
    api.rt.bus.unsubscribe(sub)
