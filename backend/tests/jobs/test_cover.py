"""World cover upload (generation-jobs task 7.1; worlds "Upload a world cover"; http-api "Cover upload route")."""

from __future__ import annotations

import io
from collections.abc import AsyncIterator

from PIL import Image

from tests.conftest import Api
from tests.jobs.kit import API, Recorder, rows

BOUNDARY = "horizonTestBoundary7MA4YWxkTrZu0gW"


def image_bytes(size: tuple[int, int], fmt: str, *, noisy: bool = False) -> bytes:
    img = Image.effect_noise(size, 60).convert("RGB") if noisy else Image.linear_gradient("L").resize(size).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()


def multipart(data: bytes, filename: str, ctype: str) -> bytes:
    head = (f"--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n").encode()
    return head + data + f"\r\n--{BOUNDARY}--\r\n".encode()


async def upload(api: Api, world: str, data: bytes, filename: str = "cover.png", ctype: str = "image/png",
                 **headers: str) -> object:
    return await api.client.post(f"{API}/worlds/{world}/cover", files={"file": (filename, data, ctype)}, headers=headers)


async def test_valid_upload(api: Api) -> None:
    rec = Recorder(api.rt)
    png = image_bytes((1100, 800), "PNG", noisy=True)
    assert len(png) > 1_000_000
    r = await upload(api, "wld_seedMeridian", png)
    assert r.status_code == 200, r.text  # type: ignore[attr-defined]
    w = r.json()  # type: ignore[attr-defined]
    assert w["cover"]["kind"] == "upload" and w["cover"]["url"] == "/assets/gen/wld_seedMeridian/cover_v1.webp"
    assert (await api.json(f"{API}/worlds/wld_seedMeridian"))["cover"] == w["cover"]
    assert any(e["type"] == "entity.changed" and e["kind"] == "world" and e.get("id") == "wld_seedMeridian" for e in rec.events)
    again = (await upload(api, "wld_seedMeridian", png)).json()  # type: ignore[attr-defined]
    assert again["cover"]["url"].endswith("cover_v2.webp")    # a new URL for every upload


async def test_stored_cover_is_a_1600x900_webp(api: Api) -> None:
    r = await upload(api, "wld_seedSunnyHollow", image_bytes((3000, 2000), "JPEG"), "photo.jpg", "image/jpeg")
    url = r.json()["cover"]["url"]  # type: ignore[attr-defined]
    assert url.startswith("/assets/gen/wld_seedSunnyHollow/")
    served = await api.get(url)
    assert served.status_code == 200 and "immutable" in served.headers["cache-control"]
    with Image.open(io.BytesIO(served.content)) as img:
        assert img.format == "WEBP" and img.size == (1600, 900)


async def test_wrong_type_too_large_or_mismatched(api: Api) -> None:
    before = (await api.json(f"{API}/worlds/wld_seedMeridian"))["cover"]
    gif = image_bytes((8, 8), "GIF")
    r = await upload(api, "wld_seedMeridian", gif, "a.gif", "image/gif")
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation"  # type: ignore[attr-defined]
    r = await upload(api, "wld_seedMeridian", b"not really a png", "b.png", "image/png")
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation"  # type: ignore[attr-defined]
    big = b"\xff\xd8\xff" + bytes(6 * 1024 * 1024)
    r = await upload(api, "wld_seedMeridian", big, "c.jpg", "image/jpeg")
    assert r.status_code == 413 and r.json()["error"]["code"] == "validation"  # type: ignore[attr-defined]
    r = await upload(api, "wld_seedMeridian", big, "c.jpg", "image/jpeg", **{"Idempotency-Key": "cover-big-1"})
    assert r.status_code == 413  # type: ignore[attr-defined]
    assert (await api.json(f"{API}/worlds/wld_seedMeridian"))["cover"] == before
    assert await rows(api, "SELECT id FROM image_assets WHERE kind = 'cover'") == []


async def test_unknown_world(api: Api) -> None:
    r = await upload(api, "wld_nope", image_bytes((16, 9), "PNG"))
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"  # type: ignore[attr-defined]


async def test_chunked_oversize_upload(api: Api) -> None:
    body = multipart(b"\x89PNG\r\n\x1a\n" + bytes(6 * 1024 * 1024), "big.png", "image/png")

    async def chunks() -> AsyncIterator[bytes]:
        for i in range(0, len(body), 256 * 1024):
            yield body[i:i + 256 * 1024]

    r = await api.client.post(f"{API}/worlds/wld_seedMeridian/cover", content=chunks(),
                              headers={"content-type": f"multipart/form-data; boundary={BOUNDARY}"})
    assert "content-length" not in {k.lower() for k in r.request.headers}
    assert r.status_code == 413 and r.json()["error"]["code"] == "validation"
    assert await rows(api, "SELECT id FROM image_assets WHERE kind = 'cover'") == []


async def test_no_key_needed_and_cover_is_kept_by_the_sweeper(api: Api) -> None:
    from horizon.runtime import sweep

    r = await upload(api, "wld_seedMeridian", image_bytes((320, 180), "PNG"))
    assert r.status_code == 200  # type: ignore[attr-defined]
    path = api.data_dir / "assets" / "gen" / "wld_seedMeridian" / "cover_v1.webp"
    assert path.is_file()
    assert sweep(api.data_dir, api.rt.referenced_files_sync(), max_age_s=0) == 0 and path.is_file()
