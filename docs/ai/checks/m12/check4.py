"""Doc 10 check 4 (rag design D22, D31.3; tasks 11.2): `pack@2` on real documents, local and free.

Run from backend/:  uv run python ../docs/ai/checks/m12/check4.py

- the two downloaded public-domain PDFs in `evals/check4/` (gitignored, never committed), converted by the app's own
  `DoclingConverter` (offline, the installed models), then chunked as a paged document;
- the 15 corpus documents, chunked as Markdown.

It writes `check4.json` beside it: per document, the piece count, sizes, locators, heading paths and the pieces this
check reads (the table pieces, the `pp. N–M` pieces, the Chinese pieces' last characters). The converted Markdown and
the pieces' full text of the PDFs stay in `evals/check4/` (their text is not committed).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from horizon.ai.chunker import CHUNKER_VERSION, chunk  # noqa: E402
from horizon.ai.converter import DoclingConverter  # noqa: E402
from horizon.config import load_config  # noqa: E402

PDFS = ROOT / "evals" / "check4"
CORPUS = ROOT / "evals" / "corpus"


def summary(name: str, md: str, *, paged: bool) -> dict[str, Any]:
    c = chunk(md, paged=paged)
    kids = c.children
    tokens = sorted(k.tokens for k in kids)
    tables = [k for k in kids if k.text.lstrip().startswith("|")]
    spans = [k for k in kids if k.page_end is not None]
    out: dict[str, Any] = {
        "doc": name, "pieces": len(kids), "pages": c.pages,
        "tokens": {"min": tokens[0], "median": tokens[len(tokens) // 2], "max": tokens[-1]} if tokens else None,
        "headings": sorted({k.heading for k in kids if k.heading})[:12],
        "pieces_starting_with_a_heading": sum(1 for k in kids if k.text.lstrip().startswith("#")),
        "table_pieces": len(tables),
        "table_pieces_repeating_the_header": sum(1 for k in tables if k.repeated > 0),
        "pp_locators": [k.locator for k in spans],
        "locators": sorted({k.locator for k in kids})[:20],
    }
    if any("一" <= ch <= "鿿" for ch in md):
        out["chinese_piece_endings"] = [k.text.rstrip()[-3:] for k in kids]
    return out


async def convert(path: Path) -> str:
    cfg = load_config()
    conv = DoclingConverter(cfg.models_dir, timeout_s=900)
    if not conv.ready():
        sys.exit("Docling is not ready (models missing): run the app's model fetch first.")
    doc = await conv.convert(path, "pdf", title=path.stem)
    (PDFS / f"{path.stem}.md").write_text(doc.markdown, encoding="utf-8")
    return doc.markdown


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    report: dict[str, Any] = {"chunker": CHUNKER_VERSION, "pdfs": [], "corpus": []}
    for pdf in sorted(PDFS.glob("*.pdf")):
        md = await convert(pdf)
        s = summary(pdf.name, md, paged=True)
        report["pdfs"].append(s)
        pieces = [{"locator": k.locator, "heading": k.heading, "tokens": k.tokens, "repeated": k.repeated,
                   "text": k.text} for k in chunk(md, paged=True).children]
        (PDFS / f"{pdf.stem}.pieces.json").write_text(json.dumps(pieces, ensure_ascii=False, indent=1), "utf-8")
        print(json.dumps(s, ensure_ascii=False)[:600])
    for f in sorted(CORPUS.glob("*/*.md")):
        md = f.read_bytes().decode("utf-8-sig")
        s = summary(f.relative_to(CORPUS).as_posix(), md, paged=False)
        report["corpus"].append({k: v for k, v in s.items() if k != "locators"})
    (HERE / "check4.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"corpus: {sum(d['pieces'] for d in report['corpus'])} pieces over {len(report['corpus'])} documents")


if __name__ == "__main__":
    asyncio.run(main())
