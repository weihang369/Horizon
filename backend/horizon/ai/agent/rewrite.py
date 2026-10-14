"""The query rewrite (doc 10 K4; rag design D10; deep-turn "The rewrite is checked, bounded and reused").

Only on a deep 1:1 or group turn whose message isn't standalone (`p < t_standalone`) or isn't English (`p < 0.5`);
debate and watch never rewrite. The request is this speaker's `agent` reply prefix byte for byte (system message 1,
the summary, the history window), then one system message with K4's instruction, so it shares (and warms) the reply's
cached prefix. Purpose `query_rewrite`, `runtime.llm.calls.query_rewrite` (thinking off, temperature 0.0, 60 tokens).

- **Checks** (K4): one line, at most 30 words, at least 60 % of its letters Latin script, not empty; else `failed`.
- **Deadline:** `retrieval.agent.rewriteMs` from its start, on the runtime clock. A late call keeps running in a
  tracked task, is still billed and recorded, and is discarded (`late`).
- **Cancelled with the turn:** cancelling the caller cancels the call (billed as the gateway bills a cancelled call).
- **Reuse:** a stored rewrite (the runtime reads it per user message and speaker) is used with no call (`stored`).
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

from horizon.ai.agent.turn import reply_prefix
from horizon.ai.contexts import TurnContext
from horizon.ai.llm import llm_request
from horizon.domain import vclock
from horizon.gateway.chat import ChatRequest

PURPOSE = "query_rewrite"
INSTRUCTION = ("Write one search query for your documents that would find what you need to reply to the last message. "
               "Make it stand on its own (no 'it', 'that' or 'there'), in English, at most 20 words. Output only the "
               "query.")
MAX_WORDS = 30
LATIN_SHARE = 0.6
RewriteStatus = Literal["ok", "stored", "failed", "late"]


@dataclass(frozen=True)
class Rewrite:
    text: str | None
    status: RewriteStatus
    task: Any = None            # the call's task, still running when `late`


def needed(standalone: float | None, english: float | None, *, t_standalone: float, t_english: float = 0.5) -> bool:
    """K4: a rewrite only when the message isn't standalone or isn't English. A fallback (None) means no rewrite."""
    if standalone is None or english is None:
        return False
    return standalone < t_standalone or english < t_english


def request(ctx: TurnContext, row: Any, model: str) -> ChatRequest:
    prefix, history, _you = reply_prefix(ctx)
    messages = [*prefix, *history, {"role": "system", "content": INSTRUCTION}]
    return llm_request(row, model, messages)


def check(text: str | None) -> str | None:
    """K4's output checks. Returns the rewrite to use, or None (failed)."""
    if text is None:
        return None
    out = text.strip().strip('"').strip()
    if not out or "\n" in out or len(out.split()) > MAX_WORDS:
        return None
    letters = [ch for ch in out if ch.isalpha()]
    if not letters:
        return None
    latin = sum(1 for ch in letters if "LATIN" in unicodedata.name(ch, ""))
    if latin / len(letters) < LATIN_SHARE:
        return None
    return re.sub(r"\s+", " ", out)


async def run(deps: Any, ctx: TurnContext, *, timeout_s: float, stored: str | None = None) -> Rewrite:
    """The rewrite for this speaker's turn: the stored one, or one call bounded by `timeout_s`."""
    if stored:
        return Rewrite(stored, "stored")
    req = request(ctx, deps.llm(PURPOSE), deps.prices.chat.model)
    cctx = ctx.call_ctx(PURPOSE)
    coro = deps.gateway().chat_complete(req, cctx)
    task: asyncio.Task[Any] = deps.spawn(f"rewrite:{ctx.speaker.id}", coro)   # tracked: a late call still lands
    try:
        done = await vclock.wait_at_most(deps.clock(), task, timeout_s)
    except asyncio.CancelledError:
        task.cancel()
        raise
    if not done:
        return Rewrite(None, "late", task)
    if task.cancelled() or task.exception() is not None:
        with contextlib.suppress(BaseException):
            task.exception()
        return Rewrite(None, "failed")
    text = check(getattr(task.result(), "content", None))
    return Rewrite(text, "ok" if text else "failed")
