"""The conversion subprocess (knowledge-memory-storage tasks 4.5, 5.1, 5.2; document-conversion "Conversions are
bounded and cancellable", "Unavailable conversion fails with a next step"; local-backend "Reset during a conversion").

A stub worker stands in for Docling, so these run in CI; the real worker is exercised by `pytest -m docling`.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from horizon.ai.converter import ConversionError, DoclingConverter
from horizon.ai.docling_worker import parent_alive, run, watchdog
from tests import docs_kit
from tests.conftest import Api
from tests.knowledge.kit import API, add_file, settle, source

STUB = Path(__file__).with_name("stub_worker.py")


class StubDocling(DoclingConverter):
    """The real subprocess runner with the stub worker; `ready` is controllable."""

    def __init__(self, tmp: Path, mode: str, *, timeout_s: float = 30, ready: bool = True) -> None:
        self.pidfile = tmp / f"{mode}.pid"
        self._ready = ready
        super().__init__(tmp, timeout_s=timeout_s,
                         command=lambda src, out: [sys.executable, str(STUB), mode, str(src), str(out), str(self.pidfile)])

    def ready(self) -> bool:
        return self._ready

    def pid(self) -> int:
        return int(self.pidfile.read_text())

    async def wait_started(self) -> int:
        for _ in range(200):
            if self.pidfile.is_file() and self.pidfile.read_text():
                return self.pid()
            await asyncio.sleep(0.05)
        raise AssertionError("the stub worker never started")


def gone(pid: int, within_s: float = 5.0) -> bool:
    deadline = time.monotonic() + within_s
    while time.monotonic() < deadline:
        if not parent_alive(pid):
            return True
        time.sleep(0.05)
    return False


def leftovers(tmp: Path) -> list[Path]:
    return list(tmp.glob(".convert-*"))


def pdf_file(tmp: Path) -> Path:
    p = tmp / "doc.pdf"
    p.write_bytes(docs_kit.pdf(["one", "two"]))
    return p


async def test_success_returns_markdown_with_pages(tmp_path: Path) -> None:
    conv = StubDocling(tmp_path, "ok")
    doc = await conv.convert(pdf_file(tmp_path), "pdf", title="doc.pdf")
    assert doc.pages == 2 and doc.paged and "<!-- page 2 -->" in doc.markdown and doc.extractor.startswith("docling@")
    assert gone(conv.pid())
    assert not leftovers(tmp_path)


async def test_timeout_kills_the_worker(tmp_path: Path) -> None:
    conv = StubDocling(tmp_path, "sleep", timeout_s=1.0)
    with pytest.raises(ConversionError) as e:
        await conv.convert(pdf_file(tmp_path), "pdf", title="doc.pdf")
    assert e.value.reason == "timeout" and "took too long" in e.value.message
    assert gone(conv.pid())


async def test_cancel_kills_the_worker(tmp_path: Path) -> None:
    conv = StubDocling(tmp_path, "sleep")
    task = asyncio.create_task(conv.convert(pdf_file(tmp_path), "pdf", title="doc.pdf"))
    pid = await conv.wait_started()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert gone(pid)
    assert not leftovers(tmp_path)


@pytest.mark.parametrize(("mode", "reason"), [("crash", "unreadable"), ("garbage", "unreadable"), ("page_limit", "page_limit")])
async def test_failures_map_to_readable_reasons(tmp_path: Path, mode: str, reason: str) -> None:
    conv = StubDocling(tmp_path, mode)
    with pytest.raises(ConversionError) as e:
        await conv.convert(pdf_file(tmp_path), "pdf", title="doc.pdf")
    assert e.value.reason == reason and e.value.message
    assert gone(conv.pid())


async def test_plain_text_never_starts_a_process(tmp_path: Path) -> None:
    p = tmp_path / "a.md"
    p.write_text("# Soups\n\nMiso first.", encoding="utf-8")
    conv = StubDocling(tmp_path, "sleep")
    doc = await conv.convert(p, "md", title="a.md")
    assert doc.markdown.startswith("# Soups") and not conv.pidfile.exists()


def test_watchdog_fires_when_the_parent_is_gone() -> None:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    fired: list[bool] = []
    watchdog(child.pid, lambda: fired.append(True), poll_s=0.02)
    deadline = time.monotonic() + 3
    while not fired and time.monotonic() < deadline:
        time.sleep(0.02)
    assert fired == [True]
    assert parent_alive(0)


def test_worker_run_protocol_with_a_fake_converter(tmp_path: Path) -> None:
    src = tmp_path / "a.docx"
    src.write_bytes(docs_kit.docx(["Hello"]))
    out = tmp_path / "out.md"
    ok = run(src, out, tmp_path, 300, convert=lambda s, m: ("# Hello", None))
    assert ok == {"ok": True, "pages": None} and out.read_text(encoding="utf-8") == "# Hello"

    def boom(_s: Path, _m: Path) -> tuple[str, int | None]:
        raise RuntimeError("internal detail /secret/path")

    bad = run(src, out, tmp_path, 300, convert=boom)
    assert bad == {"ok": False, "reason": "unreadable", "error": "Couldn't read this document."}


# ── end to end through the pipeline ──
def use(api: Api, conv: Any) -> None:
    api.rt.ai.override("converter", conv)


async def test_pdf_before_setup_fails_with_the_steps_and_keeps_the_original(api: Api, tmp_path: Path) -> None:
    use(api, StubDocling(tmp_path, "ok", ready=False))
    src = await add_file(api, "doc.pdf", docs_kit.pdf(["one", "two"]), "application/pdf")
    await settle(api)
    got = (await source(api, src["id"]))["source"]
    assert got["status"] == "failed"
    assert "npm run setup:docling" in got["error"] and "horizon models fetch" in got["error"]
    folder = api.rt.cfg.knowledge_dir / "wld_seedSunnyHollow" / "chr_seedHana" / src["id"]
    assert (folder / "original.pdf").is_file()
    # Retry after setup: the stored original converts, with no new upload.
    use(api, StubDocling(tmp_path, "ok", ready=True))
    assert (await api.client.post(f"{API}/knowledge/{src['id']}/reindex")).status_code == 200
    await settle(api)
    after = await source(api, src["id"])
    assert after["source"]["status"] == "keyword_only"
    assert [(c["text"], c["locator"]) for c in after["chunks"]] == [("Intro line.", "p. 1"),
                                                                      ("Triage starts at the door.", "p. 2")]


async def test_real_conversion_without_a_key(api_normal: Api, tmp_path: Path) -> None:
    """ai-ports "Real conversion without a key": outside test mode the real converter runs with no key."""
    assert api_normal.rt.ai.impl("converter", key_set=False) == "naive"
    use(api_normal, StubDocling(tmp_path, "ok"))
    src = await add_file(api_normal, "doc.pdf", docs_kit.pdf(["one"]), "application/pdf")
    for _ in range(200):
        got = await source(api_normal, src["id"])
        if got["source"]["status"] != "indexing":
            break
        await asyncio.sleep(0.05)
    assert got["source"]["status"] == "keyword_only" and got["chunks"][1]["text"] == "Triage starts at the door."


async def test_delete_during_conversion_kills_the_process(api: Api, tmp_path: Path) -> None:
    conv = StubDocling(tmp_path, "sleep")
    use(api, conv)
    src = await add_file(api, "doc.pdf", docs_kit.pdf(["one"]), "application/pdf")
    pid = await conv.wait_started()
    assert (await api.client.delete(f"{API}/knowledge/{src['id']}")).status_code == 204
    assert gone(pid)
    assert (await api.client.get(f"{API}/knowledge/{src['id']}")).status_code == 404


async def test_factory_reset_during_a_conversion(api: Api, tmp_path: Path) -> None:
    conv = StubDocling(tmp_path, "sleep")
    use(api, conv)
    await add_file(api, "doc.pdf", docs_kit.pdf(["one"]), "application/pdf")
    pid = await conv.wait_started()
    r = await api.client.post(f"{API}/admin/factory-reset", json={"confirm": "DELETE EVERYTHING"})
    assert r.status_code == 204, r.text
    assert gone(pid)
    from sqlalchemy import text

    async with api.rt.db.read() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM knowledge_sources WHERE is_seed = 0"))).scalar_one() == 0
