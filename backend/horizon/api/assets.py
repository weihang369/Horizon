"""`GET /assets/{path}` (doc 02 §2): `data/assets/` first, then `seed/assets/`; traversal is a 404.

Generated names are immutable, so `gen/` is served with a year-long immutable cache.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from horizon.api.common import rt_of
from horizon.api.errors import not_found

router = APIRouter()

MIME = {".svg": "image/svg+xml", ".webp": "image/webp", ".avif": "image/avif", ".png": "image/png", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".json": "application/json", ".opus": "audio/ogg", ".ogg": "audio/ogg", ".mp3": "audio/mpeg",
        ".aac": "audio/aac", ".m4a": "audio/mp4"}
IMMUTABLE = "public, max-age=31536000, immutable"


def resolve(roots: list[Path], rel: str) -> Path | None:
    clean = unquote(rel).replace("\\", "/")
    if not clean or clean.startswith("/") or any(part in ("..", "") for part in clean.split("/")) or ":" in clean:
        return None
    for root in roots:
        base = root.resolve()
        candidate = (base / clean).resolve()
        if candidate.is_relative_to(base) and candidate.is_file():
            return candidate
    return None


@router.get("/assets/{rel:path}")
async def get_asset(request: Request, rel: str) -> FileResponse:
    rt = rt_of(request)
    roots = [rt.cfg.assets_dir, rt.cfg.seed_dir / "assets"]
    if rt.cfg.static_dir:
        roots.append(rt.cfg.static_dir / "assets")  # `npm run demo`: Vite's hashed bundles live in dist/assets
    path = resolve(roots, rel)
    if path is None:
        raise not_found("Asset")
    ctype = MIME.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    headers = {"Cache-Control": IMMUTABLE if rel.startswith("gen/") else "no-cache"}
    return FileResponse(path, media_type=ctype, headers=headers)
