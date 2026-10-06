"""The image pipeline (doc 02 §2 "D-61 image pipeline", generation-jobs design D7). Pure functions over bytes.

- **Sniff** by magic bytes, never by name or declared type: PNG `89 50 4E 47`, JPEG `FF D8 FF`, WebP `RIFF....WEBP`.
- **Verify** with Pillow, with a 40 MP decompression guard read from the header before any pixel is decoded.
- **Portraits:** EXIF transpose → RGB → centre-crop to 3:4 (never stretched) → Lanczos 768×1024 → WebP `method=6`,
  quality 85, stepping down 80/75/70/65 until it is at most 250 KB.
- **Covers:** the same, centre-cropped to 16:9 at 1600×900.
- **Expression sheet:** a 2-row × 4-column grid, cut evenly (gutters ignored); each cell is cropped to 3:4 and
  scaled to 768×1024. Order: neutral, happy, sad, angry / surprised, thinking, embarrassed, eyes closed (TESTING.md A3).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageOps, UnidentifiedImageError

Format = Literal["png", "jpeg", "webp"]

MAX_PIXELS = 40_000_000
PORTRAIT_SIZE = (768, 1024)
COVER_SIZE = (1600, 900)
PORTRAIT_MAX_BYTES = 250 * 1024
COVER_MAX_BYTES = 600 * 1024
QUALITY_LADDER = (85, 80, 75, 70, 65)
SHEET_ROWS, SHEET_COLS = 2, 4
SHEET_ORDER = ("neutral", "happy", "sad", "angry", "surprised", "thinking", "embarrassed", "blink")
EXT: dict[Format, str] = {"png": "png", "jpeg": "jpg", "webp": "webp"}


class ImageRejected(ValueError):
    """Not an image we accept (wrong type, corrupt, too many pixels)."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class TooLarge(ValueError):
    """The derivative stayed over its byte budget at the lowest quality."""


@dataclass(frozen=True)
class Derived:
    data: bytes
    width: int
    height: int
    format: str = "webp"

    @property
    def size(self) -> int:
        return len(self.data)


def sniff(data: bytes) -> Format | None:
    if data[:4] == b"\x89PNG":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def open_checked(data: bytes) -> Image.Image:
    """Sniff, guard the pixel count from the header, verify, then reopen for decoding (`verify` consumes the file)."""
    if sniff(data) is None:
        raise ImageRejected("type", "Images must be PNG, JPEG or WebP.")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            w, h = probe.size
            if w * h > MAX_PIXELS:
                raise ImageRejected("pixels", f"The image is too large ({w}×{h}); at most 40 megapixels.")
            probe.verify()
        img = Image.open(io.BytesIO(data))
        img.load()
    except ImageRejected:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as e:
        raise ImageRejected("corrupt", "That file isn't a valid image.") from e
    return img


def _rgb(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img) or img
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (240, 238, 234))  # the plain warm-grey studio background
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg
    return img.convert("RGB") if img.mode != "RGB" else img


def crop_to(img: Image.Image, aspect_w: int, aspect_h: int) -> Image.Image:
    """The largest centred box of the given aspect (never a stretch)."""
    w, h = img.size
    target = aspect_w / aspect_h
    if w / h > target:
        nw = max(1, round(h * target))
        left = (w - nw) // 2
        return img.crop((left, 0, left + nw, h))
    nh = max(1, round(w / target))
    top = (h - nh) // 2
    return img.crop((0, top, w, top + nh))


def encode_webp(img: Image.Image, max_bytes: int, *, strict: bool = True) -> bytes:
    out = b""
    for q in QUALITY_LADDER:
        buf = io.BytesIO()
        img.save(buf, "WEBP", quality=q, method=6)
        out = buf.getvalue()
        if len(out) <= max_bytes:
            return out
    if strict:
        raise TooLarge(f"WebP stayed over {max_bytes} bytes at quality {QUALITY_LADDER[-1]}")
    return out


def _fit(img: Image.Image, size: tuple[int, int], max_bytes: int, *, strict: bool) -> Derived:
    framed = crop_to(_rgb(img), *size).resize(size, Image.Resampling.LANCZOS)
    return Derived(encode_webp(framed, max_bytes, strict=strict), size[0], size[1])


def portrait_webp(data: bytes) -> Derived:
    """A provider original (or a scripted placeholder) → the 768×1024 WebP the app serves."""
    return _fit(open_checked(data), PORTRAIT_SIZE, PORTRAIT_MAX_BYTES, strict=True)


def cover_webp(data: bytes) -> Derived:
    """An uploaded world cover → 1600×900 WebP (best effort under 600 KB)."""
    return _fit(open_checked(data), COVER_SIZE, COVER_MAX_BYTES, strict=False)


def sheet_cells(data: bytes) -> dict[str, Derived]:
    """Slice a 2×4 expression sheet into 8 portraits, keyed by `SHEET_ORDER` (`blink` = eyes closed)."""
    sheet = _rgb(open_checked(data))
    w, h = sheet.size
    out: dict[str, Derived] = {}
    for i, key in enumerate(SHEET_ORDER):
        r, c = divmod(i, SHEET_COLS)
        box = (round(c * w / SHEET_COLS), round(r * h / SHEET_ROWS), round((c + 1) * w / SHEET_COLS),
               round((r + 1) * h / SHEET_ROWS))
        out[key] = _fit(sheet.crop(box), PORTRAIT_SIZE, PORTRAIT_MAX_BYTES, strict=True)
    return out


def data_url(data: bytes) -> str:
    """A reference image for an edit request (doc 04 §1: references go as data URLs)."""
    import base64

    kind = sniff(data) or "png"
    return f"data:image/{kind};base64,{base64.b64encode(data).decode('ascii')}"
