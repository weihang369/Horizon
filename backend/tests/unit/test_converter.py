"""The scripted converter and conversion readiness (knowledge-memory-storage task 4.2; document-conversion spec)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from horizon.ai import converter as cv
from horizon.ai.chunker import chunk


async def test_plain_text_is_read_by_every_converter(tmp_path: Path) -> None:
    p = tmp_path / "a.md"
    p.write_bytes("﻿# Soups\n\nMiso first.".encode())
    doc = await cv.ScriptedConverter().convert(p, "md", title="a.md")
    assert doc.markdown == "# Soups\n\nMiso first." and not doc.paged and doc.extractor == "plain@1"


async def test_pdf_placeholders_follow_the_mock(tmp_path: Path) -> None:
    p = tmp_path / "r.pdf"
    p.write_bytes(b"%PDF-1.4" + b"0" * 120_000)   # ~3 pages by the mock's 40 KB rule
    doc = await cv.ScriptedConverter().convert(p, "pdf", title="Review.pdf")
    assert doc.paged and doc.pages == 3 and doc.extractor == "scripted@1"
    out = chunk(doc.markdown, paged=True)
    assert [c.locator for c in out.children] == ["p. 1", "p. 2", "p. 3"]
    assert out.children[0].text.startswith("Passage 1 of “Review.pdf”.")


async def test_docx_placeholders(tmp_path: Path) -> None:
    p = tmp_path / "n.docx"
    p.write_bytes(b"PK" + b"0" * 10)
    doc = await cv.ScriptedConverter().convert(p, "docx", title="Notes.docx")
    assert not doc.paged and doc.pages is None
    assert len(chunk(doc.markdown).children) == 1


def test_readiness_states(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    models = tmp_path / "models"
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda name, *a: None if name == "docling" else real(name, *a))  # type: ignore[misc]
    assert cv.readiness(models) == "not_installed"

    def present(name: str, *a: Any) -> Any:
        return object() if name == "docling" else real(name, *a)

    monkeypatch.setattr(importlib.util, "find_spec", present)
    assert cv.readiness(models) == "models_missing"
    models.mkdir()
    (models / "layout.bin").write_bytes(b"partial download")
    assert cv.readiness(models) == "models_missing"   # files without the marker: an interrupted fetch
    (models / cv.MODELS_MARKER).write_text("{}")
    assert cv.readiness(models) == "ready"


async def test_health_reports_models_missing_without_the_marker(api: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    real = importlib.util.find_spec

    def present(name: str, *a: Any) -> Any:
        return object() if name == "docling" else real(name, *a)

    monkeypatch.setattr(importlib.util, "find_spec", present)
    models = api.rt.cfg.models_dir
    models.mkdir(parents=True, exist_ok=True)
    (models / "some-weights.bin").write_bytes(b"x")
    body = (await api.client.get("/api/v1/health")).json()
    assert body["docling"] == "models_missing"
    (models / cv.MODELS_MARKER).write_text("{}")
    assert (await api.client.get("/api/v1/health")).json()["docling"] == "ready"
