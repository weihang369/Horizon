"""The DocumentConverter port (doc 05 §2.2; document-conversion spec; knowledge-memory-storage design D4, D5).

- **Plain text needs no converter.** MD, TXT and pasted text are read as UTF-8 by every implementation; Docling never
  sees them.
- `ScriptedConverter` (test mode's default): PDF/DOCX become deterministic placeholder passages, the MockClient's rule
  (`mock/engines/knowledge.ts` `syntheticPassages`), so CI and the portable suite never start a process. A conversion
  takes `SCRIPTED_CONVERT_S` on the runtime clock (virtual in test mode, D-82), as a Docling run takes real time: a
  source stays `extracting` until the clock moves, so in-flight behaviour (reindex → `conflict`, delete while
  indexing) is deterministic over HTTP, and the MockClient's staged pacing has a backend counterpart.
- `DoclingConverter` runs `ai/docling_worker.py` in a subprocess (below).

`readiness(models_dir)` is what `/health` reports: `not_installed` (no `docling` module), `models_missing` (no
completion marker from `horizon models fetch`, D5) or `ready`.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import json
import math
import os
import subprocess
import sys
import threading
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

Readiness = Literal["not_installed", "models_missing", "ready"]
MODELS_MARKER = ".horizon-models.json"
MAX_PAGES = 300
SCRIPTED_CONVERT_S = 0.8


@dataclass(frozen=True)
class ConvertedDoc:
    markdown: str            # with `<!-- page N -->` before each page's text when `paged`
    pages: int | None
    paged: bool
    extractor: str           # recorded as `knowledge_sources.extractor_version`


class ConversionError(Exception):
    """A document that can't be read: `reason` is page_limit | encrypted | unreadable | timeout | unavailable."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


Progress = Callable[[int, int], None]   # (pages done, pages in all)


class DocumentConverter(Protocol):
    name: str

    def ready(self) -> bool: ...
    async def convert(self, path: Path, kind: str, *, title: str, on_progress: Progress | None = None) -> ConvertedDoc: ...


def readiness(models_dir: Path) -> Readiness:
    if importlib.util.find_spec("docling") is None:
        return "not_installed"
    return "ready" if (models_dir / MODELS_MARKER).is_file() else "models_missing"


def _read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig")


async def read_plain(path: Path) -> ConvertedDoc:
    return ConvertedDoc(markdown=await asyncio.to_thread(_read_text, path), pages=None, paged=False, extractor="plain@1")


def placeholder_markdown(title: str, kind: str, size: int) -> tuple[str, int | None]:
    """The mock's synthetic passages: PDFs get one passage per page (about one page per 40 KB, at most 300 pages, at
    most six passages), DOCX one per ~60 KB (at most six)."""
    pages = min(MAX_PAGES, max(1, round(size / 40_000))) if kind == "pdf" else None
    n = max(1, min(6, pages if pages is not None else math.ceil(size / 60_000)))
    blocks = []
    for i in range(n):
        text = (f"Passage {i + 1} of “{title}”. In the live app, Docling extracts the real text of this "
                f"{kind.upper()} and these passages show it; the demo shows placeholders.")
        blocks.append(f"<!-- page {i + 1} -->\n{text}" if kind == "pdf" else text)
    return "\n\n".join(blocks), pages


class ScriptedConverter:
    name = "scripted"

    def __init__(self, sleep: Callable[[float], Awaitable[None]] | None = None) -> None:
        self.sleep = sleep

    def ready(self) -> bool:
        return True

    async def convert(self, path: Path, kind: str, *, title: str, on_progress: Progress | None = None) -> ConvertedDoc:
        if kind not in ("pdf", "docx"):
            return await read_plain(path)
        if self.sleep is not None:
            await self.sleep(SCRIPTED_CONVERT_S)
        size = (await asyncio.to_thread(path.stat)).st_size
        md, pages = placeholder_markdown(title, kind, size)
        return ConvertedDoc(markdown=md, pages=pages, paged=kind == "pdf", extractor="scripted@1")


def _docling_version() -> str:
    try:
        from importlib.metadata import version

        return version("docling")
    except Exception:
        return "unknown"


def _popen_kwargs() -> dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)}
    nice = getattr(os, "nice", None)
    return {"preexec_fn": (lambda: nice(5)) if nice is not None else None}


class DoclingConverter:
    """Docling in a subprocess (design D4): one document at a time (the caller holds `docling_slots`), offline, at
    below-normal priority, killed on cancel. The worker writes Markdown with page markers to a temporary file; on
    stdout it prints `{"progress": done, "pages": N}` after each batch of pages, then one result line
    (`{"ok": true, "pages": N}` or `{"ok": false, "reason", "error"}`). `timeout_s` bounds the wait for the NEXT
    line, not the whole document (U-80): a 19-page PDF took 4 minutes on a laptop CPU, so a fixed 600 s total failed
    every PDF past about 45 pages while it was still reading. `command` replaces the worker command line in tests (a
    stub process, no Docling needed)."""

    name = "naive"

    def __init__(self, models_dir: Path, *, timeout_s: float = 600.0,
                 command: Callable[[Path, Path], list[str]] | None = None) -> None:
        self.models_dir = models_dir
        self.timeout_s = timeout_s
        self.command = command or self._default_command

    def ready(self) -> bool:
        return readiness(self.models_dir) == "ready"

    def _default_command(self, src: Path, out: Path) -> list[str]:
        return [sys.executable, "-m", "horizon.ai.docling_worker", "--in", str(src), "--out", str(out),
                "--models", str(self.models_dir), "--max-pages", str(MAX_PAGES), "--parent", str(os.getpid())]

    async def convert(self, path: Path, kind: str, *, title: str, on_progress: Progress | None = None) -> ConvertedDoc:
        if kind not in ("pdf", "docx"):
            return await read_plain(path)
        out = path.with_name(f".convert-{uuid.uuid4().hex}.md.tmp")
        env = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
               "OMP_NUM_THREADS": str(min(4, os.cpu_count() or 1)), "PYTHONIOENCODING": "utf-8"}
        proc = await asyncio.to_thread(_spawn, self.command(path, out), env)
        lines: asyncio.Queue[str | None] = asyncio.Queue()
        _pump(proc, asyncio.get_running_loop(), lines)
        try:
            result: dict[str, Any] | None = None
            while (line := await self._next(lines)) is not None:
                obj = _json_line(line)
                if obj is None:
                    continue
                if "progress" in obj:
                    if on_progress is not None:
                        on_progress(int(obj["progress"]), int(obj.get("pages") or 0))
                    continue
                result = obj
            if result is None:
                result = {"ok": False, "reason": "unreadable", "error": "Couldn't read this document."}
            if not result.get("ok"):
                reason = str(result.get("reason") or "unreadable")
                raise ConversionError(reason, str(result.get("error") or "Couldn't read this document."))
            md = await asyncio.to_thread(out.read_text, "utf-8")
            pages = result.get("pages")
            return ConvertedDoc(markdown=md, pages=int(pages) if isinstance(pages, int) else None, paged=kind == "pdf",
                                extractor=f"docling@{_docling_version()}")
        finally:
            await asyncio.shield(asyncio.to_thread(_reap, proc))
            await asyncio.to_thread(out.unlink, True)
            # the worker writes `<out>.part` then renames it: a worker killed mid-write leaves that behind
            await asyncio.to_thread(out.with_name(out.name + ".part").unlink, True)

    async def _next(self, lines: asyncio.Queue[str | None]) -> str | None:
        try:
            return await asyncio.wait_for(lines.get(), self.timeout_s)
        except TimeoutError as e:
            raise ConversionError("timeout", "Reading this document took too long. Try a smaller file, or Retry.") from e


def _spawn(cmd: list[str], env: dict[str, str]) -> subprocess.Popen[bytes]:
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, **_popen_kwargs())


def _pump(proc: subprocess.Popen[bytes], loop: asyncio.AbstractEventLoop, lines: asyncio.Queue[str | None]) -> None:
    """Two daemon threads: stdout's lines into `lines` (then None at its end); stderr read and dropped (Docling logs
    a lot there, and a full pipe would stall the worker)."""
    def put(item: str | None) -> None:
        with contextlib.suppress(RuntimeError):   # the loop closed under a cancelled conversion
            loop.call_soon_threadsafe(lines.put_nowait, item)

    def out() -> None:
        assert proc.stdout is not None
        try:
            for raw in iter(proc.stdout.readline, b""):
                put(raw.decode("utf-8", "replace"))
        except (OSError, ValueError):   # the pipe closed by _reap
            pass
        put(None)

    def err() -> None:
        assert proc.stderr is not None
        with contextlib.suppress(OSError, ValueError):
            for _ in iter(proc.stderr.readline, b""):
                pass

    threading.Thread(target=out, name="docling-stdout", daemon=True).start()
    threading.Thread(target=err, name="docling-stderr", daemon=True).start()


def _json_line(line: str) -> dict[str, Any] | None:
    try:
        obj = json.loads(line)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _reap(proc: subprocess.Popen[bytes]) -> None:
    """Kill the worker if it is still running and wait for it, so no process is left behind."""
    if proc.poll() is None:
        proc.kill()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:  # pragma: no cover - a kill that didn't take
        pass


def download_docling_models(models_dir: Path) -> None:
    """Docling's own downloader (layout, table structure and RapidOCR models, about 1.4 GB) into `models_dir`.
    Verified against Docling 2.133 (task 5.4)."""
    from docling.utils.model_downloader import download_models

    download_models(output_dir=models_dir, progress=True)


def fetch_models(models_dir: Path, *, download: Callable[[Path], None] = download_docling_models) -> None:
    """`horizon models fetch` (design D5): remove the completion marker, download, then write the marker last, so an
    interrupted fetch leaves `models_missing` and never reads as ready."""
    if importlib.util.find_spec("docling") is None:
        raise ConversionError("unavailable", "Document conversion isn't installed. Run `npm run setup:docling` first.")
    models_dir.mkdir(parents=True, exist_ok=True)
    marker = models_dir / MODELS_MARKER
    marker.unlink(missing_ok=True)
    download(models_dir)
    from datetime import UTC, datetime

    marker.write_text(json.dumps({"docling": _docling_version(), "fetchedAt": datetime.now(UTC).isoformat()}),
                      encoding="utf-8")
