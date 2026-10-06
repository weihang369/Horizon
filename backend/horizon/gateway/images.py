"""The images client (doc backend/04 §1, D-61): `POST /api/v1/images` (Seedream 5.0 Flash by default).

`generate(...)` returns the raw image bytes plus the provider cost. The request is the shape the D-61 test run proved
(`docs/ai/image-model-test/run.mjs`, generation-jobs design D3): `model`, `prompt`, `n: 1`, `aspect_ratio`,
`resolution`, and reference images as `input_references: [{type: "image_url", image_url: {url}}]` with data URLs
(emotions are edits of the locked base portrait). The image is read from `data[].b64_json` (or a data URL) and the cost
from `usage.cost`. Post-processing (originals, WebP) lives in `horizon/storage/` (M4).
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from horizon.gateway.client import HttpCore
from horizon.gateway.errors import malformed
from horizon.gateway.types import Usage, parse_usage

PATH = "/v1/images"


@dataclass(frozen=True)
class ImageResult:
    generation_id: str | None
    images: list[bytes]
    usage: Usage | None
    provider: str | None


def _decode(item: Mapping[str, Any]) -> bytes | None:
    raw = item.get("b64_json")
    if not isinstance(raw, str):
        url = item.get("url")
        if isinstance(url, str) and url.startswith("data:") and "," in url:
            raw = url.split(",", 1)[1]
    if not isinstance(raw, str):
        return None
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        return None


class ImagesClient:
    def __init__(self, core: HttpCore, timeout_s: float) -> None:
        self.core = core
        self.timeout_s = timeout_s

    async def generate(self, *, model: str, prompt: str, refs: list[str] | None = None, resolution: str | None = None,
                       aspect_ratio: str | None = None, seed: int | None = None) -> ImageResult:
        body: dict[str, Any] = {"model": model, "prompt": prompt, "n": 1}
        for k, v in (("resolution", resolution), ("aspect_ratio", aspect_ratio), ("seed", seed)):
            if v is not None:
                body[k] = v
        if refs:
            body["input_references"] = [{"type": "image_url", "image_url": {"url": url}} for url in refs]
        resp = await self.core.request("POST", PATH, json=body, http_timeout=self.timeout_s)
        try:
            obj = resp.json()
        except ValueError as e:
            raise malformed("image response") from e
        gid = obj.get("id") if isinstance(obj, Mapping) and isinstance(obj.get("id"), str) else None
        data = obj.get("data") if isinstance(obj, Mapping) else None
        images = [b for b in (_decode(d) for d in data if isinstance(d, Mapping)) if b] if isinstance(data, list) else []
        if not images:
            raise malformed("image response", generation_id=gid)
        provider = obj.get("provider") if isinstance(obj.get("provider"), str) else None
        return ImageResult(generation_id=gid, images=images, usage=parse_usage(obj.get("usage")), provider=provider)
