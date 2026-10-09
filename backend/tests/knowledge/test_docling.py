"""Real Docling conversions (knowledge-memory-storage task 5.4; document-conversion spec). Marker `docling`: needs
`npm run setup:docling` and `horizon models fetch` on this machine, never runs in CI.

    uv run pytest -m docling tests/knowledge/test_docling.py
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

import pytest

from horizon.ai.chunker import chunk
from horizon.ai.converter import MAX_PAGES, ConversionError, DoclingConverter, readiness
from horizon.config import load_config
from tests import docs_kit

pytestmark = pytest.mark.docling
MODELS = load_config().models_dir
NO_NET = Path(__file__).with_name("_no_network_worker.py")


@pytest.fixture(autouse=True)
def _ready() -> None:
    if readiness(MODELS) != "ready":
        pytest.skip(f"Docling is {readiness(MODELS)}: run `npm run setup:docling` and `horizon models fetch`")


def write(tmp_path: Path, name: str, body: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(body)
    return p


def offline_command(src: Path, out: Path) -> list[str]:
    return [sys.executable, str(NO_NET), "--in", str(src), "--out", str(out), "--models", str(MODELS),
            "--max-pages", str(MAX_PAGES), "--parent", str(os.getpid())]


async def test_three_page_pdf_gets_page_locators(tmp_path: Path) -> None:
    pages = ["The rota starts on Monday.", "Night shifts rotate every week.", "Handover happens at seven."]
    doc = await DoclingConverter(MODELS).convert(write(tmp_path, "rota.pdf", docs_kit.pdf(pages)), "pdf", title="rota.pdf")
    assert doc.pages == 3 and doc.paged
    assert [int(n) for n in re.findall(r"<!-- page (\d+) -->", doc.markdown)] == [1, 2, 3]
    assert doc.extractor.startswith("docling@")
    locators = {c.locator for c in chunk(doc.markdown, paged=True).children}
    assert locators == {"p. 1", "p. 2", "p. 3"}


async def test_docx_headings_give_section_locators(tmp_path: Path) -> None:
    body = docs_kit.docx([("Burnout review", "Heading1"), "Shifts longer than twelve hours raise error rates.",
                          ("Recommendations", "Heading1"), "Cap shifts at ten hours and protect breaks."])
    doc = await DoclingConverter(MODELS).convert(write(tmp_path, "review.docx", body), "docx", title="review.docx")
    assert doc.pages is None and not doc.paged
    locators = [c.locator for c in chunk(doc.markdown).children]
    assert locators and all(loc.startswith("§") for loc in locators), locators
    assert any("Recommendations" in loc for loc in locators)


async def test_scanned_pdf_is_read_by_ocr(tmp_path: Path) -> None:
    body = docs_kit.image_pdf(["The night shift starts at seven"])
    doc = await DoclingConverter(MODELS).convert(write(tmp_path, "scan.pdf", body), "pdf", title="scan.pdf")
    words = re.sub(r"\s+", " ", doc.markdown.lower())
    assert "night shift starts at seven" in words, doc.markdown[:300]


async def test_over_the_page_limit_fails_fast(tmp_path: Path) -> None:
    src = write(tmp_path, "huge.pdf", docs_kit.pdf([f"Page {i}." for i in range(1, 413)]))
    t0 = time.monotonic()
    with pytest.raises(ConversionError) as e:
        await DoclingConverter(MODELS).convert(src, "pdf", title="huge.pdf")
    assert time.monotonic() - t0 < 5
    assert e.value.reason == "page_limit"
    assert "412" in e.value.message and "300" in e.value.message


async def test_conversion_makes_no_network_request(tmp_path: Path) -> None:
    src = write(tmp_path, "one.pdf", docs_kit.pdf(["Offline conversion only."]))
    doc = await DoclingConverter(MODELS, command=offline_command).convert(src, "pdf", title="one.pdf")
    assert "Offline conversion only." in doc.markdown
