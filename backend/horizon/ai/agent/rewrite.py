"""The query rewrite (doc 10 K4; rag design D10; deep-turn "The rewrite is checked, bounded and reused").

Only on a deep 1:1 or group turn whose message isn't standalone (`p < t_standalone`) or isn't English (`p < 0.5`);
debate and watch never rewrite. The request is this speaker's `agent` reply prefix byte for byte (system message 1,
the summary, the history window), then K4's instruction, so it shares (and warms) the reply's cached prefix. Purpose
`query_rewrite`, `runtime.llm.calls.query_rewrite` (thinking off, temperature 0.0, 60 tokens).

- **The instruction** is `rewrite-2` (rag 11.7, the maintainer's choice): check 3 found DeepSeek answering follow-ups in
  character when K4's wording came as a trailing system message, so it is now the last *user* message and says it is
  a search step, not a chat line, and asks for keywords.
- **Checks** (K4): one line, at most 30 words, at least 60 % of its letters Latin script, not empty; and (11.7) not
  shaped like a chat line: no second sentence, no ending in `.` or `!`. Else `failed`.
- **Deadline:** `retrieval.agent.rewriteMs` from its start, on the runtime clock. A late call keeps running in a
  tracked task, is still billed and recorded, and is discarded (`late`).
- **Cancelled with the turn:** cancelling the caller cancels the call (billed as the gateway bills a cancelled call).
- **Reuse:** a stored rewrite (the runtime reads it per user message and speaker) is used with no call (`stored`).
- **The early start** (doc 10 K15's trim 1; rag 11.9, the maintainer's choice): in 1:1, a short user message (<= 6 words)
  to a speaker with documents has its rewrite started beside Jev call 1 (`start_early`), before anyone knows a rewrite
  is needed. gather joins it (`run(early=...)`), with `rewriteMs` counted from the call's own start. When the turn is
  quick or the message needs no rewrite, the call is still billed and its answer unused (about $0.00005).
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from horizon.ai.agent.turn import reply_prefix
from horizon.ai.contexts import TurnContext
from horizon.ai.llm import llm_request
from horizon.domain import vclock
from horizon.gateway.chat import ChatRequest

PURPOSE = "query_rewrite"
INSTRUCTION = ("This is a search step, not a chat line: don't reply to the last message. Write one search query for "
               "your documents that would find what you need to reply to it. Make it stand on its own (no 'it', "
               "'that' or 'there'), in English, at most 20 words, as keywords rather than a sentence. Output only "
               "the query.")
MAX_WORDS = 30
EARLY_MAX_WORDS = 6
EARLY_KEEP = 64
LATIN_SHARE = 0.6
_CHAT_LINE = re.compile(r"[.!?。！？]\s+\S|[.!。！]$")   # a second sentence, or a line ended like a remark
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
    messages = [*prefix, *history, {"role": "user", "content": INSTRUCTION}]
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
    if latin / len(letters) < LATIN_SHARE or _CHAT_LINE.search(out):
        return None
    return re.sub(r"\s+", " ", out)


EarlyKey = tuple[str, str, str]
_EARLY: OrderedDict[EarlyKey, tuple[asyncio.Task[Any], datetime]] = OrderedDict()


def _settled(task: asyncio.Task[Any]) -> None:
    if not task.cancelled():
        task.exception()


def early_key(ctx: TurnContext, message_id: str | None) -> EarlyKey | None:
    return (ctx.session.session_id, ctx.speaker.id, message_id) if message_id else None


def start_early(deps: Any, ctx: TurnContext, message: str, message_id: str | None) -> None:
    """K15's trim 1: start this speaker's rewrite of a short message now, for gather to join (one call either way)."""
    key = early_key(ctx, message_id)
    if key is None or key in _EARLY or len(message.split()) > EARLY_MAX_WORDS:
        return
    req = request(ctx, deps.llm(PURPOSE), deps.prices.chat.model)
    task: asyncio.Task[Any] = deps.spawn(f"rewrite-early:{ctx.speaker.id}",
                                         deps.gateway().chat_complete(req, ctx.call_ctx(PURPOSE)))
    task.add_done_callback(_settled)   # a failed call nobody joins (a quick turn) is still retrieved
    _EARLY[key] = (task, deps.clock().now())
    while len(_EARLY) > EARLY_KEEP:   # an unused early call (a quick turn) is dropped here, long settled
        _EARLY.popitem(last=False)


async def run(deps: Any, ctx: TurnContext, *, timeout_s: float, stored: str | None = None,
              early: EarlyKey | None = None) -> Rewrite:
    """The rewrite for this speaker's turn: the stored one, the early call joined, or one call bounded by `timeout_s`
    from its start."""
    if stored:
        return Rewrite(stored, "stored")
    joined = _EARLY.pop(early, None) if early is not None else None
    task: asyncio.Task[Any]
    if joined is not None and not joined[0].cancelled():
        task, started = joined
        timeout_s = max(0.0, timeout_s - (deps.clock().now() - started).total_seconds())
    else:
        req = request(ctx, deps.llm(PURPOSE), deps.prices.chat.model)
        task = deps.spawn(f"rewrite:{ctx.speaker.id}", deps.gateway().chat_complete(req, ctx.call_ctx(PURPOSE)))
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
