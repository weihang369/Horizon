"""Knowledge upload validation (knowledge-memory-storage task 3.1; knowledge-sources "Accepted inputs")."""

from __future__ import annotations

from pathlib import Path

import pytest

from horizon.api.errors import HorizonHTTPError
from horizon.services.knowledge import validate as v
from tests import docs_kit


def write(tmp: Path, name: str, data: bytes) -> Path:
    p = tmp / name
    p.write_bytes(data)
    return p


def code_of(fn: object, *a: object) -> tuple[str, dict[str, object]]:
    with pytest.raises(HorizonHTTPError) as e:
        fn(*a)  # type: ignore[operator]
    return e.value.code, dict(e.value.details or {})


@pytest.mark.parametrize(("name", "mime", "kind"), [
    ("notes.pdf", "application/pdf", "pdf"), ("a.docx", v.DOCX_MIME, "docx"), ("a.md", "text/markdown", "md"),
    ("a.markdown", "", "md"), ("a.MD", "text/plain", "md"), ("a.txt", "text/plain", "txt"),
    ("a.pdf", "application/octet-stream", "pdf"), ("a.txt", "text/plain; charset=utf-8", "txt"),
])
def test_supported_names(name: str, mime: str, kind: str) -> None:
    assert v.kind_of(name, mime) == kind


@pytest.mark.parametrize(("name", "mime"), [
    ("sheet.csv", "text/csv"), ("notes.html", "text/html"), ("page", ""), ("a.xlsx", ""), ("a.pdf.exe", ""),
])
def test_unsupported_names(name: str, mime: str) -> None:
    code, details = code_of(v.kind_of, name, mime)
    assert code == "validation" and details["field"] == "file"


def test_declared_type_must_fit_the_extension() -> None:
    code, details = code_of(v.kind_of, "fake.pdf", "text/plain")
    assert code == "validation" and details["mime"] == "text/plain"


def test_real_documents_pass(tmp_path: Path) -> None:
    v.check_content(write(tmp_path, "a.pdf", docs_kit.pdf(["Page one."])), "pdf")
    v.check_content(write(tmp_path, "a.docx", docs_kit.docx(["Hello"])), "docx")
    v.check_content(write(tmp_path, "a.md", "﻿# Soups\n\nMiso first.".encode()), "md")
    v.check_content(write(tmp_path, "a.txt", "Tea — 3 min.".encode()), "txt")


def test_fake_pdf(tmp_path: Path) -> None:
    code, details = code_of(v.check_content, write(tmp_path, "fake.pdf", b"not a pdf"), "pdf")
    assert code == "validation" and details["reason"] == "content_mismatch"


def test_spreadsheet_renamed_docx(tmp_path: Path) -> None:
    code, _ = code_of(v.check_content, write(tmp_path, "report.docx", docs_kit.xlsx()), "docx")
    assert code == "validation"


def test_plain_zip_renamed_docx(tmp_path: Path) -> None:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", "hi")
    assert code_of(v.check_content, write(tmp_path, "a.docx", buf.getvalue()), "docx")[0] == "validation"
    assert code_of(v.check_content, write(tmp_path, "b.docx", b"PK\x03\x04garbage"), "docx")[0] == "validation"


def test_binary_renamed_txt(tmp_path: Path) -> None:
    code, details = code_of(v.check_content, write(tmp_path, "notes.txt", b"\xff\xfe\x00h\x00i"), "txt")
    assert code == "validation" and details["reason"] == "not_utf8"
    assert code_of(v.check_content, write(tmp_path, "nul.md", b"ok\x00ok"), "md")[0] == "validation"


def test_pasted_text_rules() -> None:
    ok = v.check_text("  Notes  ", "Rice first.")
    assert ok.title == "Notes" and ok.data == b"Rice first."
    assert v.check_text("x" * 300, "a").title == "x" * 200
    assert code_of(v.check_text, "", "text")[1]["field"] == "title"
    assert code_of(v.check_text, "T", "   \n ")[1]["field"] == "text"
    code, details = code_of(v.check_text, "Long", "a" * (210 * 1024))
    assert code == "validation" and details["limit"] == 204800
    v.check_text("Edge", "a" * 204800)  # exactly the limit is fine


def test_size_errors_carry_the_limit() -> None:
    e = v.too_large_file(11 * 1024 * 1024)
    assert e.status == 413 and e.code == "validation" and (e.details or {})["limit"] == 10485760
    assert (v.too_many_sources().details or {})["limit"] == 20
