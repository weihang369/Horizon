"""The chunker (knowledge-memory-storage task 4.1; knowledge-sources "Passages carry readable locators")."""

from __future__ import annotations

import re

from horizon.ai.chunker import CHUNKER_VERSION, chunk


def collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def test_markdown_paragraphs_match_the_mock() -> None:
    md = "# Soups\n\nMiso first.\n\nThen tofu."
    out = chunk(md)
    assert [c.text for c in out.children] == ["# Soups", "Miso first.", "Then tofu."]
    assert [c.locator for c in out.children] == ["§ Soups"] * 3
    assert CHUNKER_VERSION == "para@1"


def test_plain_text_gets_paragraph_locators_and_collapsed_whitespace() -> None:
    out = chunk("Steep   for\nthree minutes.\r\n\r\n\r\nServe hot.")
    assert [c.text for c in out.children] == ["Steep for three minutes.", "Serve hot."]
    assert [c.locator for c in out.children] == ["¶ 1", "¶ 2"]


def test_pdf_pages_from_markers() -> None:
    md = "<!-- page 1 -->\nIntro line.\n<!-- page 2 -->\nTriage starts at the door.\n\nThen vitals.\n<!-- page 3 -->\nEnd."
    out = chunk(md, paged=True)
    by_text = {c.text: c.locator for c in out.children}
    assert by_text["Triage starts at the door."] == "p. 2"
    assert by_text["Intro line."] == "p. 1" and by_text["End."] == "p. 3"
    assert out.pages == 3
    [s] = out.sections
    assert (s.page_start, s.page_end) == (1, 3)


def test_long_paragraph_is_cut_at_a_sentence_end() -> None:
    sentence = "This sentence is about forty characters. "
    para = (sentence * 75).strip()   # ~3 000 chars
    out = chunk(para)
    pieces = [c.text for c in out.children]
    assert len(pieces) >= 3 and all(len(p) <= 1200 for p in pieces)
    assert all(p.endswith(".") for p in pieces[:-1])
    assert " ".join(pieces) == para


def test_offsets_slice_back_to_each_child() -> None:
    md = "# Heading\n\nFirst   para\nwraps here.\n\n" + ("Word salad sentence goes here. " * 60) + "\n\nLast."
    out = chunk(md)
    for c in out.children:
        assert collapse(md[c.char_start:c.char_end]) == c.text, c


def test_sections_follow_headings_and_close_near_the_cap() -> None:
    md = "# A\n\none\n\ntwo\n\n## B\n\nthree\n\n# C\n\n" + "\n\n".join(f"para {i} " + "x" * 400 for i in range(20))
    out = chunk(md)
    paths = [s.heading_path for s in out.sections]
    assert paths[0] == "A" and paths[1] == "A › B" and all(p == "C" for p in paths[2:])
    assert len(paths) > 3            # C is split near 1 500 tokens
    assert all(s.tokens <= 1500 + 110 for s in out.sections)
    assert out.children[4].text == "three" and out.children[4].heading == "B" and out.children[4].locator == "§ B"


def test_empty_document_has_no_children() -> None:
    assert chunk("  \n\n <!-- page 1 -->\n\n").children == []
