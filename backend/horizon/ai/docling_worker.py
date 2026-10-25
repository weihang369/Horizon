"""The document conversion worker process (knowledge-memory-storage design D4; document-conversion spec).

    python -m horizon.ai.docling_worker --in FILE --out MD --models DIR --max-pages 300 --parent PID

Run by `DoclingConverter`, one process per document, offline (`HF_HUB_OFFLINE=1`). It:
1. counts a PDF's pages first (pypdfium2 ships with Docling) and stops early past `--max-pages`, so a 900-page PDF
   fails in milliseconds instead of after minutes of OCR; a password-protected PDF stops as `encrypted`;
2. converts with Docling, models from `--models` (verified against Docling 2.133, task 5.4). A PDF is read a few
   pages at a time, and OCR is chosen per page (U-80): a page with no text layer (a scan, or outlined text) is OCRed
   page-whole with RapidOCR on torch (Docling's default region OCR returns duplicated fragments on a page that is one
   big bitmap); a page with text and a picture of real size is OCRed on its bitmaps (Docling's default); a page of
   plain text skips OCR, which on a text PDF was 85 % of the time and found nothing (19 pages: 4 min → 22 s, the
   same Markdown). After each batch it prints `{"progress": done, "pages": N}`, so the bar moves and the parent can
   tell a slow document from a stuck one;
3. writes Markdown to `--out`, with `<!-- page N -->` before each page's text (PDF);
4. ends with exactly one result line: `{"ok": true, "pages": N}` or `{"ok": false, "reason": …, "error": …}`.

A watchdog thread exits the process when its parent is gone: Windows doesn't kill children with their parent, so a
hard-killed server must not leave a conversion running.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

POLL_S = 1.0
BATCH_PAGES = 3          # pages per Docling call: the bar moves every few seconds; batching costs no extra time
MIN_IMAGE_SHARE = 0.02   # a picture under 2 % of the page (a logo, a bullet icon) doesn't make the page need OCR

OcrMode = Literal["none", "bitmaps", "full_page"]


class Refused(Exception):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


def parent_alive(pid: int) -> bool:
    if pid <= 0:
        return True
    if sys.platform == "win32":   # not `os.name`: mypy narrows on sys.platform, so Linux CI skips the windll branch
        import ctypes

        synchronize, wait_timeout = 0x00100000, 0x00000102
        kernel32 = ctypes.windll.kernel32  # Windows only
        handle = kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return False
        try:
            return bool(kernel32.WaitForSingleObject(handle, 0) == wait_timeout)
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def watchdog(parent: int, on_gone: Callable[[], None], *, poll_s: float = POLL_S,
             alive: Callable[[int], bool] = parent_alive) -> threading.Thread:
    """Start a daemon thread that calls `on_gone` once `parent` stops running."""
    def loop() -> None:
        while alive(parent):
            time.sleep(poll_s)
        on_gone()

    th = threading.Thread(target=loop, name="parent-watchdog", daemon=True)
    th.start()
    return th


def count_pdf_pages(path: Path) -> int:
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as e:
        if "password" in str(e).lower():
            raise Refused("encrypted", "This PDF is password-protected. Remove the password and add it again.") from e
        raise Refused("unreadable", "Couldn't read this PDF.") from e
    try:
        return len(pdf)
    finally:
        pdf.close()


def page_ocr_modes(path: Path) -> list[OcrMode]:
    """The OCR each page of a PDF needs: `full_page` with no text layer, `bitmaps` with text and a picture of at
    least MIN_IMAGE_SHARE of the page, else `none`."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    pdf = pdfium.PdfDocument(str(path))
    modes: list[OcrMode] = []
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            textpage = page.get_textpage()
            try:
                if not textpage.get_text_range().strip():
                    modes.append("full_page")
                    continue
                area = max(1.0, float(page.get_width()) * float(page.get_height()))
                big = False
                for obj in page.get_objects(filter=(pdfium_c.FPDF_PAGEOBJ_IMAGE,)):
                    left, bottom, right, top = obj.get_bounds()
                    if (right - left) * (top - bottom) >= MIN_IMAGE_SHARE * area:
                        big = True
                        break
                modes.append("bitmaps" if big else "none")
            finally:
                textpage.close()
                page.close()
    finally:
        pdf.close()
    return modes


def batches(modes: list[OcrMode], size: int = BATCH_PAGES) -> list[tuple[int, int, OcrMode]]:
    """Runs of consecutive pages with the same OCR mode, at most `size` pages each: (first, last, mode), 1-based."""
    out: list[tuple[int, int, OcrMode]] = []
    for n, mode in enumerate(modes, start=1):
        if out and out[-1][2] == mode and out[-1][1] - out[-1][0] + 1 < size:
            out[-1] = (out[-1][0], n, mode)
        else:
            out.append((n, n, mode))
    return out


def print_progress(done: int, total: int) -> None:
    print(json.dumps({"progress": done, "pages": total}), flush=True)


def convert_with_docling(src: Path, models: Path,
                         report: Callable[[int, int], None] = print_progress) -> tuple[str, int | None]:
    """Docling 2.x: Markdown per page with markers for PDF, batch by batch with OCR chosen per page; one Markdown
    body for DOCX."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import OcrMode as DoclingOcrMode
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    def converter(mode: OcrMode) -> Any:
        opts = PdfPipelineOptions(artifacts_path=str(models))
        opts.do_ocr = mode != "none"
        if mode == "full_page":
            opts.ocr_options = RapidOcrOptions(backend="torch", mode=DoclingOcrMode.FULL_PAGE)
        return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})

    if src.suffix.lower() != ".pdf":
        return str(converter("bitmaps").convert(str(src)).document.export_to_markdown()), None
    modes = page_ocr_modes(src)
    convs: dict[str, Any] = {}
    parts: dict[int, str] = {}
    for first, last, mode in batches(modes):
        if mode not in convs:   # one converter per mode: its models load once
            convs[mode] = converter(mode)
        doc: Any = convs[mode].convert(str(src), page_range=(first, last)).document
        for p in doc.pages:
            parts[int(p)] = doc.export_to_markdown(page_no=int(p))
        report(last, len(modes))
    page_nos = sorted(parts)
    return "\n\n".join(f"<!-- page {n} -->\n{parts[n]}" for n in page_nos), len(page_nos)


def run(src: Path, out: Path, models: Path, max_pages: int,
        convert: Callable[[Path, Path], tuple[str, int | None]] = convert_with_docling) -> dict[str, Any]:
    try:
        if src.suffix.lower() == ".pdf":
            pages = count_pdf_pages(src)
            if pages > max_pages:
                raise Refused("page_limit", f"This document has {pages} pages; the limit is {max_pages}.")
        md, n = convert(src, models)
    except Refused as e:
        return {"ok": False, "reason": e.reason, "error": e.message}
    except Exception as e:  # Docling's own failures: unreadable, with no internals leaked to the user
        print(f"conversion failed: {type(e).__name__}: {e}", file=sys.stderr)
        return {"ok": False, "reason": "unreadable", "error": "Couldn't read this document."}
    tmp = out.with_name(out.name + ".part")
    tmp.write_text(md, encoding="utf-8")
    os.replace(tmp, out)
    return {"ok": True, "pages": n}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="horizon.ai.docling_worker")
    p.add_argument("--in", dest="src", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--models", required=True)
    p.add_argument("--max-pages", type=int, default=300)
    p.add_argument("--parent", type=int, default=0)
    a = p.parse_args(argv)
    watchdog(a.parent, lambda: os._exit(3))
    result = run(Path(a.src), Path(a.out), Path(a.models), a.max_pages)
    print(json.dumps(result), flush=True)
    return 0 if result["ok"] else 2


if __name__ == "__main__":  # pragma: no cover - the subprocess entry
    sys.exit(main())
