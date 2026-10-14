"""`horizon space build [--space ID] [--yes]` (rag design D5; local-backend "Command-line interface").

1. Refuse while a backend holds the data directory (`storage.datalock`), so no live search sees a half-built space.
2. Start the runtime offline, count what the build would embed and copy (`plan_build`), and print the tokens and the
   estimated cost at today's price period.
3. Ask (or take `--yes`). With no confirmation (an answer other than yes, or no terminal to answer from), spend
   nothing and say why.
4. Build (`build_space`): copy what wouldn't change, embed the rest, flip.

There is no route and no UI (K3, D-91).
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable

from horizon.config import Config
from horizon.db import spaces
from horizon.db.spaces import DEFAULT_SPACE, PLAIN_SPACE, SpaceSpec
from horizon.storage.datalock import held_elsewhere

KNOWN: dict[str, SpaceSpec] = {s.id: s for s in (DEFAULT_SPACE, PLAIN_SPACE)}


def run(cfg: Config, space_id: str | None, yes: bool, *, ask: Callable[[str], str] | None = None,
        out: Callable[[str], None] = print) -> int:
    spec = KNOWN.get(space_id or DEFAULT_SPACE.id)
    if spec is None:
        out(f"horizon: unknown space {space_id!r}; known: {', '.join(sorted(KNOWN))}")
        return 2
    if held_elsewhere(cfg.data_dir):
        out(f"horizon: a backend is running on {cfg.data_dir}. Stop it, then run `horizon space build` again.")
        return 2
    return asyncio.run(_run(cfg, spec, yes, ask, out))


async def _run(cfg: Config, spec: SpaceSpec, yes: bool, ask: Callable[[str], str] | None,
               out: Callable[[str], None]) -> int:
    from horizon.runtime import Runtime
    from horizon.services.knowledge.build import build_space, plan_build

    rt = Runtime(cfg)
    await rt.start()
    try:
        async with rt.db.read() as conn:
            active = await spaces.active(conn)
        if active.id == spec.id:
            out(f"horizon: {spec.id} is already the active space; nothing to build.")
            return 0
        plan = await plan_build(rt, spec)
        period = rt.clock.pricing_period()
        out(f"horizon: build {spec.id} (from {active.id})")
        out(f"  embed {plan.chunks} passages and {plan.memories} memories: {plan.tokens:,} tokens, "
            f"about ${plan.cost_usd:.6f} ({period} prices)")
        out(f"  copy {plan.copy_chunks} passage and {plan.copy_memories} memory vectors (no request, no cost)")
        if not yes:
            if ask is None and not sys.stdin.isatty():
                out("horizon: nothing was spent. Re-run with --yes to confirm the build.")
                return 1
            answer = (ask or input)("Build it? [y/N] ").strip().lower()
            if answer not in ("y", "yes"):
                out("horizon: nothing was spent; the active space is unchanged.")
                return 1
        if rt.keys.status() != "set":
            out("horizon: an OpenRouter key is needed to build an embedding space. Set one in Settings first.")
            return 2
        report = await build_space(rt, spec)
        out(f"horizon: {spec.id} is active ({report.chunks} passages and {report.memories} memories embedded; "
            f"{report.copied_chunks} and {report.copied_memories} copied)")
        return 0
    finally:
        await rt.stop()
