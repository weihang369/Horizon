"""Tiny documents generated at test time (knowledge-memory-storage; no committed binaries).

- `pdf(pages)`: a valid text PDF, one page per string (Helvetica, plain ASCII), readable by any PDF parser.
- `image_pdf(lines)`: an image-only ("scanned") PDF made with Pillow: no text layer, so only OCR can read it.
- `docx(paragraphs)`: a minimal WordprocessingML package; `(text, "Heading1")` makes a heading. It carries a
  `styles.xml` naming the heading styles, as every Word file does (Docling reads heading levels from style names).
- `xlsx()`: a minimal spreadsheet package (a ZIP without `word/document.xml`).
"""

from __future__ import annotations

import io
import zipfile


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf(pages: list[str]) -> bytes:
    objs: list[bytes] = []
    n = len(pages)
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    font_id = 3 + 2 * n
    for i, text in enumerate(pages):
        content = f"BT /F1 12 Tf 72 720 Td ({_esc(text)}) Tj ET".encode()
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_id} 0 R >> >> "
                    f"/Contents {4 + 2 * i} 0 R >>".encode())
        objs.append(b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def image_pdf(lines: list[str]) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (1700, 2200), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=64)
    for i, line in enumerate(lines):
        draw.text((150, 200 + i * 120), line, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PDF", resolution=200.0)
    return buf.getvalue()


_CT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
       '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
       '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
       '<Default Extension="xml" ContentType="application/xml"/>'
       '<Override PartName="/word/document.xml" '
       'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
       '<Override PartName="/word/styles.xml" '
       'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
         '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
         'Target="word/document.xml"/></Relationships>')


_DOC_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
             'Target="styles.xml"/></Relationships>')
_STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
           + "".join(f'<w:style w:type="paragraph" w:styleId="Heading{n}"><w:name w:val="heading {n}"/>'
                     f'<w:basedOn w:val="Normal"/><w:pPr><w:outlineLvl w:val="{n - 1}"/></w:pPr></w:style>'
                     for n in (1, 2, 3))
           + '</w:styles>')


def docx(paragraphs: list[str | tuple[str, str]]) -> bytes:
    body = []
    for p in paragraphs:
        text, style = (p, None) if isinstance(p, str) else p
        ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        body.append(f"<w:p>{ppr}<w:r><w:t xml:space=\"preserve\">{text}</w:t></w:r></w:p>")
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           + "".join(body) + "</w:body></w:document>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/document.xml", doc)
        z.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        z.writestr("word/styles.xml", _STYLES)
    return buf.getvalue()


def xlsx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/workbook.xml", "<workbook/>")
        z.writestr("xl/worksheets/sheet1.xml", "<worksheet/>")
    return buf.getvalue()
