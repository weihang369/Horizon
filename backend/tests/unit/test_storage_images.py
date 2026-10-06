"""The image pipeline and atomic writes (generation-jobs task 1.2, design D7)."""

from __future__ import annotations

import io
import random
import struct
import zlib
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw

from horizon.storage import atomic
from horizon.storage import images as im


def encode(img: Image.Image, fmt: str) -> bytes:
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()


def grainy(size: int = 1024) -> Image.Image:
    """A busy picture with camera grain: shapes over a gradient, plus Gaussian noise."""
    base = Image.linear_gradient("L").resize((size, size)).convert("RGB")
    d = ImageDraw.Draw(base)
    rng = random.Random(1)
    for _ in range(60):
        x, y, r = rng.randrange(size), rng.randrange(size), rng.randrange(20, 200)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(rng.randrange(256), rng.randrange(256), rng.randrange(256)))
    noise = Image.effect_noise((size, size), 24).convert("RGB")
    dim = ImageChops.multiply(base, Image.new("RGB", (size, size), (230, 230, 230)))
    return ImageChops.add(dim, ImageChops.subtract(noise, Image.new("RGB", (size, size), (110, 110, 110))))


def png_header_only(width: int, height: int) -> bytes:
    """A PNG whose IHDR claims `width × height` (valid CRC), with no pixel data behind it."""
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"")) + chunk(b"IEND", b"")


def test_sniff_by_magic_bytes() -> None:
    assert im.sniff(encode(Image.new("RGB", (4, 4)), "PNG")) == "png"
    assert im.sniff(encode(Image.new("RGB", (4, 4)), "JPEG")) == "jpeg"
    assert im.sniff(encode(Image.new("RGB", (4, 4)), "WEBP")) == "webp"
    assert im.sniff(encode(Image.new("RGB", (4, 4)), "GIF")) is None
    assert im.sniff(b"hello, I am a text file") is None


def test_seedream_jpeg_becomes_768x1024_webp() -> None:
    src = encode(grainy().resize((832, 1110)), "JPEG")
    out = im.portrait_webp(src)
    assert (out.width, out.height) == (768, 1024)
    with Image.open(io.BytesIO(out.data)) as img:
        assert img.format == "WEBP" and img.size == (768, 1024)
    assert out.size <= im.PORTRAIT_MAX_BYTES


def test_busy_square_image_stays_under_budget() -> None:
    out = im.portrait_webp(encode(grainy(), "PNG"))
    assert out.size <= 250 * 1024


def test_pure_noise_over_budget_fails() -> None:
    noise = Image.frombytes("RGB", (1024, 1024), random.Random(2).randbytes(1024 * 1024 * 3))
    with pytest.raises(im.TooLarge):
        im.portrait_webp(encode(noise, "PNG"))


def test_crop_never_stretches() -> None:
    wide = Image.new("RGB", (4000, 1000), (10, 20, 30))
    assert im.crop_to(wide, 3, 4).size == (750, 1000)
    tall = Image.new("RGB", (900, 3000))
    assert im.crop_to(tall, 3, 4).size == (900, 1200)


@pytest.mark.parametrize("data,reason", [
    (encode(Image.new("RGB", (8, 8)), "GIF"), "type"),
    (b"not really a png at all", "type"),
    (b"\x89PNG\r\n\x1a\n" + b"garbage" * 10, "corrupt"),
    (png_header_only(8000, 7000), "pixels"),
])
def test_rejected_inputs(data: bytes, reason: str) -> None:
    with pytest.raises(im.ImageRejected) as e:
        im.portrait_webp(data)
    assert e.value.reason == reason


def test_cover_is_1600x900() -> None:
    out = im.cover_webp(encode(grainy().resize((3000, 2000)), "JPEG"))
    assert (out.width, out.height) == (1600, 900)
    with Image.open(io.BytesIO(out.data)) as img:
        assert img.size == (1600, 900)


def test_sheet_slices_into_eight_portraits() -> None:
    sheet = Image.new("RGB", (1536, 1024))
    d = ImageDraw.Draw(sheet)
    for i in range(8):
        r, c = divmod(i, 4)
        d.rectangle((c * 384, r * 512, (c + 1) * 384 - 1, (r + 1) * 512 - 1), fill=(i * 30, 100, 200 - i * 20))
    cells = im.sheet_cells(encode(sheet, "PNG"))
    assert list(cells) == list(im.SHEET_ORDER)
    for i, key in enumerate(im.SHEET_ORDER):
        cell = cells[key]
        assert (cell.width, cell.height) == (768, 1024)
        with Image.open(io.BytesIO(cell.data)) as img:
            px = img.convert("RGB").getpixel((384, 512))
        assert isinstance(px, tuple)
        assert abs(px[0] - i * 30) < 12  # each cell is its own grid square


def test_atomic_write_and_crash_leaves_only_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "gen" / "w" / "c" / "portrait_happy_v2.webp"
    atomic.write_atomic(target, b"first")
    assert target.read_bytes() == b"first"
    assert [p.name for p in target.parent.iterdir()] == [target.name]

    crash_target = target.with_name("portrait_sad_v2.webp")

    def crash(_a: object, _b: object) -> None:
        raise RuntimeError("power cut")

    monkeypatch.setattr(atomic.os, "replace", crash)
    with pytest.raises(RuntimeError):
        atomic.write_atomic(crash_target, b"second")
    names = sorted(p.name for p in target.parent.iterdir())
    assert not crash_target.exists()
    assert len(names) == 2 and any(n.startswith("portrait_sad_v2.webp.") and n.endswith(".tmp") for n in names)


def test_replace_retries_a_windows_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}
    real = atomic.os.replace

    def flaky(a: str, b: str) -> None:
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("locked")
        real(a, b)

    monkeypatch.setattr(atomic.os, "replace", flaky)
    monkeypatch.setattr(atomic, "REPLACE_DELAY_S", 0.0)
    atomic.write_atomic(tmp_path / "x.bin", b"ok")
    assert (tmp_path / "x.bin").read_bytes() == b"ok" and calls["n"] == 3


def test_data_url_names_the_type() -> None:
    assert im.data_url(encode(Image.new("RGB", (2, 2)), "JPEG")).startswith("data:image/jpeg;base64,")
