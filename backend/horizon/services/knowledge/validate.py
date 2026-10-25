"""Knowledge upload validation (knowledge-sources "Accepted inputs", "Knowledge limits"; design D3; D-65).

A file is judged by its **extension and its content**:
- the extension must be `pdf | docx | md | markdown | txt`, and a declared MIME type, when present and specific, must
  fit it (the MockClient's rule, so `notes.html` and `sheet.csv` fail the same way on both clients);
- PDF: `%PDF-` within the first 1 KB;
- DOCX: a ZIP whose central directory lists `word/document.xml` (names only: nothing is extracted, so a ZIP bomb costs
  nothing here; a plain ZIP or an XLSX fails);
- MD / TXT: strict UTF-8 (a BOM allowed) with no NUL byte.

Pasted text needs a title and non-blank text of at most 200 KB of UTF-8. Every refusal is `validation` with
`details.field` (and `details.limit` for a size), and nothing is created.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from horizon.api.errors import HorizonHTTPError, validation

FileKind = Literal["pdf", "docx", "md", "txt"]

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TEXT_BYTES = 200 * 1024
MAX_SOURCES = 20
MAX_PAGES = 300
MAX_CHUNKS = 3000
TITLE_MAX = 200

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_EXT: dict[str, tuple[FileKind, tuple[str, ...]]] = {
    "pdf": ("pdf", ("application/pdf",)),
    "docx": ("docx", (DOCX_MIME,)),
    "md": ("md", ("text/markdown", "text/x-markdown", "text/plain")),
    "markdown": ("md", ("text/markdown", "text/x-markdown", "text/plain")),
    "txt": ("txt", ("text/plain",)),
}
ACCEPTED = ["pdf", "docx", "md", "txt"]
MIME_OF: dict[FileKind, str] = {"pdf": "application/pdf", "docx": DOCX_MIME, "md": "text/markdown", "txt": "text/plain"}
GENERIC_MIMES = {"", "application/octet-stream"}


@dataclass(frozen=True)
class PastedText:
    title: str
    data: bytes


def unsupported() -> HorizonHTTPError:
    return validation("Add a PDF, DOCX, Markdown or text file. CSV, spreadsheets and links aren't supported.",
                      {"field": "file", "accepted": ACCEPTED})


def kind_of(filename: str | None, mime: str | None) -> FileKind:
    """The kind a file claims to be, from its name and declared type (before its content is read)."""
    ext = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    if ext not in _EXT:
        raise unsupported()
    kind, mimes = _EXT[ext]
    declared = (mime or "").split(";", 1)[0].strip().lower()
    if declared not in GENERIC_MIMES and declared not in mimes:
        raise validation(f"That file's type ({declared}) doesn't match .{ext}.", {"field": "file", "mime": declared})
    return kind


def _not_real(kind: FileKind) -> HorizonHTTPError:
    return validation(f"This doesn't look like a real .{kind} file.", {"field": "file", "reason": "content_mismatch"})


def check_content(path: Path, kind: FileKind) -> None:
    """Confirm the bytes on disk are what the name claims (raises `validation`)."""
    if kind == "pdf":
        with path.open("rb") as f:
            if b"%PDF-" not in f.read(1024):
                raise _not_real(kind)
        return
    if kind == "docx":
        try:
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
        except (zipfile.BadZipFile, OSError) as e:
            raise _not_real(kind) from e
        if "word/document.xml" not in names:
            raise _not_real(kind)
        return
    data = path.read_bytes()
    if b"\x00" in data:
        raise _not_utf8(kind)
    try:
        data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise _not_utf8(kind) from e


def _not_utf8(kind: FileKind) -> HorizonHTTPError:
    return validation(f"This .{kind} file isn't UTF-8 text.", {"field": "file", "reason": "not_utf8"})


def check_text(title: str | None, text: str | None) -> PastedText:
    t = (title or "").strip()
    if not t:
        raise validation("Give the pasted text a title.", {"field": "title"})
    if not (text or "").strip():
        raise validation("Paste some text first.", {"field": "text"})
    data = (text or "").encode("utf-8")
    if len(data) > MAX_TEXT_BYTES:
        raise validation("Pasted text can be at most 200 KB.", {"field": "text", "limit": MAX_TEXT_BYTES,
                                                                "bytes": len(data)})
    return PastedText(title=t[:TITLE_MAX], data=data)


def too_large_file(size: int | None = None) -> HorizonHTTPError:
    details: dict[str, object] = {"field": "file", "limit": MAX_FILE_BYTES}
    if size is not None:
        details["bytes"] = size
    return HorizonHTTPError("validation", "Files can be at most 10 MB.", status=413, details=details)


def too_many_sources() -> HorizonHTTPError:
    return validation(f"A character can have at most {MAX_SOURCES} sources. Delete one first.",
                      {"field": "sources", "limit": MAX_SOURCES})
