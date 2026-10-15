"""The chunker, `pack@2` (doc 10 K1; rag design D3, tasks 1.1–1.2; knowledge-sources "Pieces are sized by structure,
then by length", "Tables and lists keep their lines", "Passages carry readable locators").

The shared fixtures in `tests/fixtures/chunker/` are read here and by the MockClient's twin (`knowledge.test.ts`)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from horizon.ai.chunker import CHUNKER_VERSION, MAX, TARGET, chunk
from horizon.domain.pricing import count_tokens

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "chunker"
CASES = sorted(FIXTURES.glob("*.json"))
_MARKER = re.compile(r"^\s*<!--\s*(?:page\s+\d+|image)\s*-->\s*$", re.IGNORECASE | re.MULTILINE)


def collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def load(p: Path) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    return doc


def test_the_fixture_set_covers_the_cases() -> None:
    assert {p.stem for p in CASES} >= {
        "soups", "heading_carry", "heading_page_foot", "merge_300", "ceiling_cuts", "cjk_cuts", "table_split",
        "list_kept", "page_break_mid_sentence", "heading_change", "paragraph_numbers", "image_markers",
        "table_wide_header"}


@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_every_fixture(path: Path) -> None:
    doc = load(path)
    out = chunk(doc["markdown"], paged=doc["paged"])
    got = [{"text": c.text, "locator": c.locator, "heading": c.heading} for c in out.children]
    assert got == doc["pieces"]


@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_the_offsets_invariant(path: Path) -> None:
    """Each piece's text, without a repeated table header, is the collapsed source between its offsets with page-marker
    lines dropped; and no piece passes the ceiling."""
    doc = load(path)
    md = doc["markdown"]
    for c in chunk(md, paged=doc["paged"]).children:
        source = _MARKER.sub("", md[c.char_start:c.char_end])
        assert collapse(c.text[c.repeated:]) == collapse(source), c
        assert c.tokens == count_tokens(c.text) <= MAX


def test_one_chunker_version() -> None:
    assert CHUNKER_VERSION == "pack@2"
    backend = Path(__file__).resolve().parents[2] / "horizon"
    defs = [p for p in backend.rglob("*.py") if re.search(r"^CHUNKER_VERSION\s*=", p.read_text(encoding="utf-8"), re.M)]
    assert [p.name for p in defs] == ["chunker.py"]


def test_soups_is_one_piece() -> None:
    [c] = chunk("# Soups\n\nMiso first.\n\nThen tofu.").children
    assert (c.text, c.locator, c.heading) == ("# Soups\n\nMiso first.\n\nThen tofu.", "§ Soups", "Soups")


def test_short_paragraphs_merge_under_their_heading() -> None:
    para = ("Rest days are kept clear of on-call work. " * 6).strip()     # ≈ 80 tokens
    assert 70 <= count_tokens(para) <= 90
    [c] = chunk("## Long shift blocks\n\n" + "\n\n".join([para] * 3)).children
    assert c.text.startswith("## Long shift blocks\n\n") and c.text.count(para) == 3


def test_a_long_paragraph_splits_at_sentence_ends() -> None:
    para = " ".join(f"Sentence {i} says the ward keeps a spare nurse on nights." for i in range(60))
    assert count_tokens(para) > 800
    out = chunk(para).children
    assert len(out) >= 3 and all(c.tokens <= MAX for c in out)
    assert all(c.text.endswith(".") for c in out)
    assert all(abs(c.tokens - TARGET) < 40 for c in out[:-1])
    assert " ".join(c.text for c in out) == para


def test_chinese_is_cut_after_a_full_stop() -> None:
    para = "".join(f"第{i}条：护士在连续三个长班之后应当休息两天，病房主管负责安排替班人员。" for i in range(40))
    out = chunk(para).children
    assert len(out) >= 2 and all(c.text.endswith("。") for c in out)


def test_a_long_table_repeats_its_header() -> None:
    rows = "\n".join(f"| ward {i} | {i} nurses | covered by the night team on rota {i} |" for i in range(60))
    out = chunk("| Ward | Staff | Note |\n|---|---|---|\n" + rows).children
    assert len(out) >= 2
    for c in out:
        assert c.text.startswith("| Ward | Staff | Note |\n|---|---|---|\n| ward ")
        assert c.tokens <= MAX
    assert [c.repeated > 0 for c in out] == [False] + [True] * (len(out) - 1)


def test_pdf_pages_from_markers() -> None:
    md = ("<!-- page 1 -->\nIntro line.\n<!-- page 2 -->\nTriage starts at the door.\n\nThen vitals.\n"
          "<!-- page 3 -->\nEnd.")
    out = chunk(md, paged=True)
    by_text = {c.text: c.locator for c in out.children}
    assert by_text["Triage starts at the door.\n\nThen vitals."] == "p. 2"
    assert by_text["Intro line."] == "p. 1" and by_text["End."] == "p. 3"
    assert out.pages == 3


def test_a_sentence_across_a_page_break_is_one_piece() -> None:
    md = "<!-- page 3 -->\nThe nurse who meets the patient\n<!-- page 4 -->\nrecords the first vitals.\n"
    [c] = chunk(md, paged=True).children
    assert (c.text, c.locator) == ("The nurse who meets the patient records the first vitals.", "pp. 3–4")


def test_a_full_sentence_before_a_page_break_closes_the_piece() -> None:
    md = "<!-- page 3 -->\nThe nurse meets the patient.\n<!-- page 4 -->\nShe records the first vitals.\n"
    assert [c.locator for c in chunk(md, paged=True).children] == ["p. 3", "p. 4"]


def test_sections_follow_headings_and_close_near_the_cap() -> None:
    long = " ".join(f"Para {i} sentence about the night rota and its cover." for i in range(30))
    md = "# A\n\none\n\ntwo\n\n## B\n\nthree\n\n# C\n\n" + "\n\n".join([long] * 8)
    out = chunk(md)
    paths = [s.heading_path for s in out.sections]
    assert paths[0] == "A" and paths[1] == "A › B" and all(p == "C" for p in paths[2:])
    assert len(paths) > 3            # C is split near 1 500 tokens
    assert all(s.tokens <= 1500 + MAX for s in out.sections)
    b = out.children[1]
    assert b.text == "## B\n\nthree" and b.heading == "A › B" and b.locator == "§ B"


def test_trailing_headings_and_empty_documents_make_no_piece() -> None:
    assert chunk("  \n\n <!-- page 1 -->\n\n").children == []
    assert [c.text for c in chunk("Body.\n\n# Appendix\n\n## Empty").children] == ["Body."]
