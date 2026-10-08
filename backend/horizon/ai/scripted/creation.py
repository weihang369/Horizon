"""Scripted creation ports (generation-jobs design D9; ai-ports "Profile drafter", "Image generator", "Song generator").

- `ScriptedDrafter`: the mock's draft bank (`drafts.py`), billed per task at the price table's share like the
  MockClient (four `profile` tasks at `profileDraft / 4`).
- `ScriptedImageGenerator`: a deterministic placeholder drawn with Pillow (palette background, a silhouette and the
  emotion name, seeded by the task ID), billed at the task's image price.
- `ProceduralSong`: the procedural theme (D-83): free, no ledger row, paced like the mock's song. The naive song
  generator (Lyria 3 Clip, D-87) lives in `ai/naive/creation.py`.

Both paid ports run through the gateway's scripted source (`scripted_generation`): the same preflight, hooks and
ledger row as a real call, paced on the backend clock, and never a connection.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from horizon.ai.ports import ImageJob, PaidHooks, SongJob
from horizon.ai.scripted import drafts
from horizon.ai.scripted.ports import AiDeps
from horizon.gateway.context import CallContext
from horizon.services import theme


def _rgb(hex_colour: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    h = hex_colour.lstrip("#")
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)) if len(h) == 6 else fallback
    except ValueError:
        return fallback


def placeholder_png(job: ImageJob) -> bytes:
    """The scripted portrait: deterministic for the same task ID (same bytes every time)."""
    from PIL import Image, ImageDraw

    sheet = job.mode == "sheet"
    w, h = (1536, 1024) if sheet else (832, 1110)
    seed = hashlib.sha256(job.task_id.encode("utf-8")).digest()
    stage = _rgb(job.palette[0], (40, 40, 52))
    primary = _rgb(job.palette[1], (90, 120, 200))
    secondary = _rgb(job.palette[2], (230, 230, 240))
    img = Image.new("RGB", (w, h), stage)
    draw = ImageDraw.Draw(img)
    cells = [(c * w // 4, r * h // 2, (c + 1) * w // 4, (r + 1) * h // 2) for r in range(2) for c in range(4)] if sheet \
        else [(0, 0, w, h)]
    labels = ["neutral", "happy", "sad", "angry", "surprised", "thinking", "embarrassed", "blink"] if sheet else [job.label]
    for (x0, y0, x1, y1), label in zip(cells, labels, strict=True):
        cw, ch = x1 - x0, y1 - y0
        jitter = seed[len(label) % len(seed)] % 24 - 12
        draw.ellipse((x0 + cw * 0.34 + jitter, y0 + ch * 0.12, x0 + cw * 0.66 + jitter, y0 + ch * 0.40), fill=primary)
        draw.rounded_rectangle((x0 + cw * 0.18, y0 + ch * 0.44, x0 + cw * 0.82, y0 + ch * 1.02), radius=max(4, cw // 9),
                               fill=primary)
        draw.text((x0 + cw * 0.08, y0 + ch * 0.9), label, fill=secondary, font_size=max(12, cw // 14))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


class ScriptedDrafter:
    shared_call = False

    def __init__(self, deps: AiDeps, palette_ids: Callable[[], Sequence[str]]) -> None:
        self.deps = deps
        self.palette_ids = palette_ids

    def expected_ms(self, duration_ms: float) -> float:
        return duration_ms

    async def draft(self, ctx: CallContext, *, seed_prompt: str, intent: str, cost_usd: float, duration_ms: float,
                    model: str, hooks: PaidHooks) -> dict[str, Any]:
        async def produce() -> dict[str, Any]:
            await self.deps.clock().sleep(duration_ms / 1000)
            return drafts.draft_from_seed(seed_prompt, intent, self.palette_ids())

        return await self.deps.gateway().scripted_generation(
            ctx, cost_usd=cost_usd, model=model, produce=produce, before_send=hooks.before_send,
            after_response=hooks.after_response, commit_with=hooks.commit_with)

    async def regenerate_field(self, ctx: CallContext, *, profile: Mapping[str, Any], field: str, attempt: int,
                               cost_usd: float, duration_ms: float, model: str, hooks: PaidHooks) -> dict[str, Any]:
        async def produce() -> dict[str, Any]:
            await self.deps.clock().sleep(duration_ms / 1000)
            return drafts.regenerate_field(profile, field, attempt)

        return await self.deps.gateway().scripted_generation(
            ctx, cost_usd=cost_usd, model=model, produce=produce, before_send=hooks.before_send,
            after_response=hooks.after_response, commit_with=hooks.commit_with)


class ScriptedImageGenerator:
    name = "scripted"

    def __init__(self, deps: AiDeps) -> None:
        self.deps = deps

    def expected_ms(self, job: ImageJob) -> float:
        return job.duration_ms

    async def generate(self, ctx: CallContext, job: ImageJob, hooks: PaidHooks) -> bytes:
        async def produce() -> bytes:
            await self.deps.clock().sleep(job.duration_ms / 1000)
            return await asyncio.to_thread(placeholder_png, job)

        return await self.deps.gateway().scripted_generation(
            ctx, cost_usd=self.deps.prices.generation[job.price_kind], model=job.model, produce=produce,
            before_send=hooks.before_send, after_response=hooks.after_response, commit_with=hooks.commit_with)


class ProceduralSong:
    model = theme.MODEL
    paid = False

    def expected_ms(self, duration_ms: float) -> float:
        return duration_ms

    def theme(self, seed: str, brief: Mapping[str, Any], title: str | None) -> dict[str, Any]:
        return theme.theme_spec_from_brief(seed, brief, title)

    async def generate(self, ctx: CallContext, job: SongJob, hooks: PaidHooks) -> bytes:
        raise NotImplementedError("the procedural theme makes no call")
