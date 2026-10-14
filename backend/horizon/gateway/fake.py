"""FakeOpenRouter (design D14, provider-gateway "Test mode never reaches the network").

An `httpx.MockTransport` handler that answers every endpoint the gateway uses, in-process and deterministically. It is
the provider in test mode (`HORIZON_TEST=1`), so the TS HTTP contract suite and integration tests run the real
gateway code with no socket ever opened.

- A bearer starting `sk-or-bad` gets 401 everywhere (the portable "bad key" test).
- Chat answers "ok" (SSE or JSON) from provider DeepSeek; decisions take the first option / 0.5 / the middle level;
  embeddings are deterministic unit vectors; every paid answer carries a generation ID and `usage.cost`.
- Images (M4) answer a deterministic PNG in `data[0].b64_json` sized for the requested aspect ratio (3:4 → 832×1110,
  Seedream's 1K size), with `usage.cost` from the price table.
- Music (creation-followups D1): a chat request asking for `modalities` with `"audio"` streams a silent MP3 stub
  (`storage.audio.silent_mp3`) as base64 `delta.audio` pieces with `usage.cost` 0.04. `music_mode` switches it to
  `"fail"` (503 with a body: nothing charged), `"stall"` (keepalives only, so the client times out) or `"not_mp3"`
  (WAV-looking bytes). Music requests are also counted under `counts["music"]`.
- `counts` tallies requests per endpoint, so tests can assert exactly how many provider calls were made, and
  `park_image(n)` holds the n-th images request open on an event (the restart tests' "request in flight").
- Embeddings (knowledge-memory-storage): `park_embedding(n)` holds the n-th embeddings request the same way, and
  `embed_dims` forces the returned length (a provider that ignores `dimensions`, or returns short vectors).
- ai-foundation (docs/ai/13 W14, design D39): chat requests carry the test-mode `X-Horizon-Purpose` header, and
  `canned[purpose]` answers that purpose with recorded real responses, in turn (cycling), streamed or complete;
  `load_canned(set)` reads a committed set from `tests/fixtures/canned/`. `park_decision(n)` holds the n-th decisions
  request. Jev answers carry `type` and count tokens at UTF-8 bytes / 3, the shape group A recorded.
- rag (M12 design D2): `park_questions(prefix, n)` holds the next n decisions requests asking a matching question
  (a deep turn's 8 `passage:` checks), each released on its own event in any order; `answer_question(pattern, raw)`
  answers a question key (or a `prefix*`) with a set raw answer; `refuse_question(prefix)` answers the next request
  asking it with HTTP 429 (Jev's rate limit), once. Every "needs documents?" (`docs:…`) is answered no (0.0) unless a
  test sets it, so a character with documents stays on the quick path by default. A queued streamed (SSE) response
  waits for a chat request: a Jev request in between (a gate riding the plan) never takes it.

The response shapes follow the recorded fixtures in `tests/fixtures/openrouter/` (unverified until the live run).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import math
from collections import Counter
from collections.abc import Awaitable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx

from horizon.domain import vclock

CHAT_COST = 0.000002
DECISION_COST_PER_M = 0.042
EMBED_COST_PER_M = 0.01
IMAGE_COST = 0.018
MUSIC_COST = 0.04
KEEPALIVE = ": OPENROUTER PROCESSING\n\n"
NOT_MP3 = b"RIFF" + bytes(4) + b"WAVEfmt " + bytes(64)   # a WAV-looking header: not a usable clip
CANNED_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "canned"
PURPOSE_HEADER = "x-horizon-purpose"
CREDITS_TOTAL = 5.0
CREDITS_USED = 0.79
DEFAULT_DIMS = 1024
# A 1×1 transparent PNG (kept for tests that need a tiny decodable image).
PNG_1PX = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
# Seedream's 1K output sizes per aspect ratio (the D-61 run returned 832×1110 for 3:4).
IMAGE_SIZES = {"3:4": (832, 1110), "3:2": (1536, 1024), "16:9": (1600, 900), "1:1": (1024, 1024)}
ENDPOINTS = {("GET", "/v1/key"): "key", ("GET", "/v1/credits"): "credits", ("GET", "/v1/models"): "models",
             ("GET", "/v1/generation"): "generation", ("POST", "/v1/chat/completions"): "chat",
             ("POST", "/alpha/decisions"): "decisions", ("POST", "/v1/embeddings"): "embeddings",
             ("POST", "/v1/images"): "images"}


def fake_png(prompt: str, aspect_ratio: str | None) -> bytes:
    """A deterministic placeholder portrait: a plain tinted background and a silhouette, seeded by the prompt."""
    from PIL import Image, ImageDraw

    w, h = IMAGE_SIZES.get(aspect_ratio or "3:4", IMAGE_SIZES["3:4"])
    d = hashlib.sha256(prompt.encode("utf-8")).digest()
    img = Image.new("RGB", (w, h), (200 + d[0] % 40, 196 + d[1] % 40, 190 + d[2] % 40))
    draw = ImageDraw.Draw(img)
    tone = (40 + d[3] % 120, 40 + d[4] % 120, 60 + d[5] % 120)
    draw.ellipse((w * 0.35, h * 0.12, w * 0.65, h * 0.42), fill=tone)
    draw.rounded_rectangle((w * 0.2, h * 0.45, w * 0.8, h * 1.05), radius=int(w * 0.12), fill=tone)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()



def _wants_audio(request: httpx.Request) -> bool:
    try:
        return "audio" in (json.loads(request.content).get("modalities") or [])
    except (ValueError, AttributeError):
        return False


class _Stall(httpx.AsyncByteStream):
    """A music stream that only ever sends keepalive comments (the client's first-audio deadline fires)."""

    async def __aiter__(self) -> Any:
        yield KEEPALIVE.encode("ascii")
        while True:
            await asyncio.sleep(3600)
            yield KEEPALIVE.encode("ascii")


def _tokens(value: Any) -> int:
    return max(1, math.ceil(len(json.dumps(value, ensure_ascii=False).encode("utf-8")) / 4))


def _jev_tokens(value: Any) -> int:
    return max(1, math.ceil(len(json.dumps(value, ensure_ascii=False).encode("utf-8")) / 3))


def load_canned(name: str, root: Path = CANNED_DIR) -> tuple[str, list[dict[str, Any]]]:
    """A committed canned-response set: `(purpose, responses)`. Unknown names raise `KeyError`."""
    if not name or not name.replace("-", "").replace("_", "").isalnum():
        raise KeyError(name)
    p = root / f"{name}.json"
    if not p.is_file():
        raise KeyError(name)
    doc = json.loads(p.read_text(encoding="utf-8"))
    return str(doc["purpose"]), list(doc["responses"])


def unit_vector(text: str, dims: int) -> list[float]:
    raw = [b / 255 - 0.5 for b in hashlib.shake_256(text.encode("utf-8")).digest(dims)]
    norm = math.sqrt(sum(x * x for x in raw)) or 1.0
    return [x / norm for x in raw]


class FakeOpenRouter:
    def __init__(self, models: Iterable[str] = (), *, image_cost: float = IMAGE_COST) -> None:
        self.models = set(models)
        self.image_cost = image_cost
        self._n = 0
        self.costs: dict[str, float] = {}  # generation id → cost, for /generation lookups
        self.requests: list[httpx.Request] = []
        self.queued: list[httpx.Response] = []  # test hook: answered first, in order (e.g. a 500 or a 401)
        self.counts: Counter[str] = Counter()   # requests received per endpoint (`ENDPOINTS` names)
        self._parks: dict[int, asyncio.Event] = {}
        self.parked = asyncio.Event()             # set once a parked images request is being held
        self.music_mode = "ok"                    # ok | fail | stall | not_mp3
        self._embed_parks: dict[int, asyncio.Event] = {}
        self.embed_parked = asyncio.Event()       # set once a parked embeddings request is being held
        self.embed_dims: int | None = None        # force the returned vector length (None: honour `dimensions`)
        self._decision_parks: dict[int, asyncio.Event] = {}
        self.decision_parked = asyncio.Event()    # set once a parked decisions request is being held
        self._chat_parks: dict[str, asyncio.Event] = {}   # purpose -> the next chat request with it is held (M11)
        self._question_parks: list[tuple[str, asyncio.Event]] = []   # a question key prefix -> the next decisions
                                                                     # request asking it is held (M11)
        self.chat_parked = asyncio.Event()        # set once a parked chat request is being held
        self.canned: dict[str, list[Mapping[str, Any]]] = {}   # purpose -> recorded responses, answered in turn
        self._canned_i: Counter[str] = Counter()
        self._set_answers: dict[str, dict[str, Any]] = {}  # question key, or "prefix*" -> raw answer (M12)
        self._refusals: list[tuple[str, int]] = []           # question key prefix -> HTTP status, once each (M12)

    def park_image(self, n: int) -> asyncio.Event:
        """Hold the n-th images request (1-based, counted over this fake's life) until the returned event is set."""
        ev = asyncio.Event()
        self._parks[n] = ev
        return ev

    def park_embedding(self, n: int) -> asyncio.Event:
        """Hold the n-th embeddings request (1-based, over this fake's life) until the returned event is set."""
        ev = asyncio.Event()
        self._embed_parks[n] = ev
        return ev

    def park_decision(self, n: int) -> asyncio.Event:
        """Hold the n-th decisions request (1-based, over this fake's life) until the returned event is set."""
        ev = asyncio.Event()
        self._decision_parks[n] = ev
        return ev

    def park_question(self, prefix: str) -> asyncio.Event:
        """Hold the next decisions request holding a question whose key starts with `prefix` (M11: the debate plan's
        `member_rebuttal`, its `emotion_line:` faces) until the returned event is set; counting-free, so other Jev
        requests in between (reactions, the face check) don't move it."""
        ev = asyncio.Event()
        self._question_parks.append((prefix, ev))
        return ev

    def park_questions(self, prefix: str, n: int) -> list[asyncio.Event]:
        """Hold the next `n` decisions requests asking a question whose key starts with `prefix`, each on its own event
        (M12 D2: a deep turn's parallel `passage:` checks, released in any order)."""
        return [self.park_question(prefix) for _ in range(n)]

    def answer_question(self, pattern: str, raw: Mapping[str, Any] | None) -> None:
        """Answer question key `pattern` (or every key starting with it, for `prefix*`) with `raw`, Jev's answer shape
        (`{"type": "noul", "noul": 0.8}`); None removes it. Other keys keep the default answers."""
        if raw is None:
            self._set_answers.pop(pattern, None)
        else:
            self._set_answers[pattern] = dict(raw)

    def refuse_question(self, prefix: str, status: int = 429) -> None:
        """Answer the next decisions request asking a question whose key starts with `prefix` with `status` (Jev's
        429 rate limit by default), once."""
        self._refusals.append((prefix, status))

    def _set_answer(self, key: str) -> dict[str, Any] | None:
        if key in self._set_answers:
            return self._set_answers[key]
        hits = [p for p in self._set_answers if p.endswith("*") and key.startswith(p[:-1])]
        return self._set_answers[max(hits, key=len)] if hits else None

    def park_chat(self, purpose: str) -> asyncio.Event:
        """Hold the next chat request labelled `purpose` (the test-mode purpose header) until the returned event is set
        (debate D2: a host line or a verdict waiting on DeepSeek). The caller's activity token is given up while held."""
        ev = asyncio.Event()
        self._chat_parks[purpose] = ev
        return ev

    def set_canned(self, purpose: str, responses: Sequence[Mapping[str, Any]] | None) -> None:
        if responses:
            self.canned[purpose] = list(responses)
            self._canned_i[purpose] = 0
        else:
            self.canned.pop(purpose, None)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)  # type: ignore[arg-type]  # sync answers, or a held (async) one

    def _gen(self, prefix: str, cost: float) -> str:
        self._n += 1
        gid = f"{prefix}-fake-{self._n:06d}"
        self.costs[gid] = cost
        return gid

    def handle(self, request: httpx.Request) -> httpx.Response | Awaitable[httpx.Response]:
        self.requests.append(request)
        path = request.url.path.removeprefix("/api")
        route = (request.method, path)
        self.counts[ENDPOINTS.get(route, "other")] += 1
        if route == ("POST", "/v1/chat/completions") and b'"audio"' in request.content and _wants_audio(request):
            self.counts["music"] += 1
        park = self._parks.pop(self.counts["images"], None) if route == ("POST", "/v1/images") else None
        if park is not None:
            return self._held(park, request)
        epark = self._embed_parks.pop(self.counts["embeddings"], None) if route == ("POST", "/v1/embeddings") else None
        if epark is not None:
            return self._held(epark, request, flag=self.embed_parked)
        dpark = self._decision_parks.pop(self.counts["decisions"], None) if route == ("POST", "/alpha/decisions") else None
        if dpark is None and route == ("POST", "/alpha/decisions") and self._question_parks:
            keys = list(json.loads(request.content or b"{}").get("questions") or {})
            hit = next((i for i, (pre, _) in enumerate(self._question_parks) if any(k.startswith(pre) for k in keys)),
                       None)
            if hit is not None:
                dpark = self._question_parks.pop(hit)[1]
        if dpark is not None:
            return self._held(dpark, request, flag=self.decision_parked, idle=True)
        if route == ("POST", "/v1/chat/completions") and self._chat_parks:
            cpark = self._chat_parks.pop(request.headers.get(PURPOSE_HEADER) or "", None)
            if cpark is not None:
                return self._held(cpark, request, flag=self.chat_parked, idle=True)
        return self._answer(request, route)

    async def _held(self, park: asyncio.Event, request: httpx.Request, *, flag: asyncio.Event | None = None,
                    idle: bool = False) -> httpx.Response:
        """`idle`: the caller's activity token is given up while held, so virtual time can advance past a deadline
        (a parked Jev decision); it is taken back when the request is released."""
        (flag or self.parked).set()
        holder = vclock.current_holder() if idle else None
        if holder is not None:
            holder.drop()
        try:
            await park.wait()
        finally:
            if holder is not None:
                holder.hold()
        return self._answer(request, (request.method, request.url.path.removeprefix("/api")))

    def _answer(self, request: httpx.Request, route: tuple[str, str]) -> httpx.Response:
        if self.queued and (route == ("POST", "/v1/chat/completions")
                            or self.queued[0].headers.get("content-type") != "text/event-stream"):
            return self.queued.pop(0)
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer sk-or-") or auth.startswith("Bearer sk-or-bad"):
            return httpx.Response(401, json={"error": {"code": 401, "message": "No auth credentials found"}})
        path = route[1]
        body: Any = json.loads(request.content) if request.content else None
        if route == ("GET", "/v1/key"):
            return httpx.Response(200, json={"data": {"label": "fake", "usage": CREDITS_USED, "limit": None,
                                                      "limit_remaining": None, "is_free_tier": False}})
        if route == ("GET", "/v1/credits"):
            return httpx.Response(200, json={"data": {"total_credits": CREDITS_TOTAL, "total_usage": CREDITS_USED}})
        if route == ("GET", "/v1/models"):
            return httpx.Response(200, json={"data": [{"id": m} for m in sorted(self.models)]})
        if route == ("GET", "/v1/generation"):
            gid = request.url.params.get("id", "")
            if gid not in self.costs:
                return httpx.Response(404, json={"error": {"code": 404, "message": "Generation not found"}})
            return httpx.Response(200, json={"data": {"id": gid, "total_cost": self.costs[gid], "provider_name": "DeepSeek"}})
        if route == ("POST", "/v1/chat/completions"):
            if "audio" in (body.get("modalities") or []):
                return self._music(body)
            purpose = request.headers.get(PURPOSE_HEADER)
            if purpose and self.canned.get(purpose):
                return self._canned(purpose, body)
            return self._chat(body)
        if route == ("POST", "/alpha/decisions"):
            keys = list((body or {}).get("questions") or {})
            hit = next((i for i, (pre, _) in enumerate(self._refusals) if any(k.startswith(pre) for k in keys)), None)
            if hit is not None:
                status = self._refusals.pop(hit)[1]
                return httpx.Response(status, headers={"retry-after": "1"},
                                      json={"error": {"code": status, "message": "Rate limit exceeded"}})
            return self._decide(body)
        if route == ("POST", "/v1/embeddings"):
            return self._embed(body)
        if route == ("POST", "/v1/images"):
            gid = self._gen("gen", self.image_cost)
            png = base64.b64encode(fake_png(str(body.get("prompt", "")), body.get("aspect_ratio"))).decode("ascii")
            return httpx.Response(200, json={"id": gid, "model": body.get("model"), "provider": "Seed",
                                             "data": [{"b64_json": png, "media_type": "image/png"}],
                                             "usage": {"cost": self.image_cost}})
        return httpx.Response(404, json={"error": {"code": 404, "message": f"No fake for {request.method} {path}"}})

    def _chat(self, body: dict[str, Any]) -> httpx.Response:
        gid = self._gen("gen", CHAT_COST)
        prompt = _tokens(body.get("messages"))
        usage = {"prompt_tokens": prompt, "completion_tokens": 1, "total_tokens": prompt + 1,
                 "prompt_tokens_details": {"cached_tokens": 0}, "cost": CHAT_COST}
        base = {"id": gid, "model": body.get("model"), "provider": "DeepSeek"}
        if not body.get("stream"):
            return httpx.Response(200, json={**base, "object": "chat.completion", "usage": usage, "choices": [
                {"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}]})
        chunks = [
            {**base, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"role": "assistant", "content": "ok"},
                                                                       "finish_reason": None}]},
            {**base, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
             "usage": usage},
        ]
        text = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=text.encode("utf-8"))

    def _canned(self, purpose: str, body: dict[str, Any]) -> httpx.Response:
        """The purpose's next recorded response (cycling), as JSON or as SSE in three pieces."""
        items = self.canned[purpose]
        rec = items[self._canned_i[purpose] % len(items)]
        self._canned_i[purpose] += 1
        u = dict(rec.get("usage") or {})
        cost = float(u.get("cost", CHAT_COST))
        gid = self._gen("gen", cost)
        usage = {**u, "cost": cost}
        content = str(rec.get("content", ""))
        finish = rec.get("finish_reason") or "stop"
        base = {"id": gid, "model": body.get("model"), "provider": rec.get("provider") or "DeepSeek"}
        if not body.get("stream"):
            return httpx.Response(200, json={**base, "object": "chat.completion", "usage": usage, "choices": [
                {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish}]})
        third = max(1, len(content) // 3)
        pieces = [content[:third], content[third:2 * third], content[2 * third:]] if content else []
        chunks = [{**base, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": x},
                                                                          "finish_reason": None}]} for x in pieces if x]
        chunks.append({**base, "object": "chat.completion.chunk",
                       "choices": [{"index": 0, "delta": {}, "finish_reason": finish}], "usage": usage})
        text = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=text.encode("utf-8"))

    def _music(self, body: dict[str, Any]) -> httpx.Response:
        sse = {"content-type": "text/event-stream"}
        if self.music_mode == "fail":
            return httpx.Response(503, json={"error": {"code": 503, "message": "No endpoints available"}})
        if self.music_mode == "stall":
            return httpx.Response(200, headers=sse, stream=_Stall())
        from horizon.storage.audio import silent_mp3

        gid = self._gen("gen", MUSIC_COST)
        clip = NOT_MP3 if self.music_mode == "not_mp3" else silent_mp3(8)
        data = base64.b64encode(clip).decode("ascii")
        third = len(data) // 3
        base = {"id": gid, "model": body.get("model"), "provider": "Google AI Studio", "object": "chat.completion.chunk"}
        chunks = [{**base, "choices": [{"index": 0, "delta": {"audio": {"data": piece}}, "finish_reason": None}]}
                  for piece in (data[:third], data[third:2 * third], data[2 * third:])]
        chunks.append({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                       "usage": {"prompt_tokens": _tokens(body.get("messages")), "completion_tokens": 0, "cost": MUSIC_COST}})
        text = KEEPALIVE + "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, headers=sse, content=text.encode("utf-8"))

    def _decide(self, body: dict[str, Any]) -> httpx.Response:
        answers: dict[str, Any] = {}
        for key, q in (body.get("questions") or {}).items():
            kind, crit = q.get("type"), q.get("criteria")
            if kind == "choice":
                opts = list(crit or {})
                p = 1 / len(opts) if opts else 1.0
                answers[key] = {"type": "choice", "choice": opts[0] if opts else None, "confidence": p,
                                "probabilities": dict.fromkeys(opts, p)}
            elif kind == "noul":
                answers[key] = {"type": "noul", "noul": 0.0 if key.startswith("docs:") else 0.5}
            elif kind == "score":
                levels = list(crit or [])
                mid = (len(levels) - 1) / 2
                answers[key] = {"type": "score", "score": mid, "confidence": 1.0,
                                "probabilities": {str(i): (1.0 if i == round(mid) else 0.0) for i in range(len(levels))},
                                "legend": levels}
            set_raw = self._set_answer(key)
            if set_raw is not None:
                answers[key] = dict(set_raw)
        # Jev bills the state once plus each question (group A A1); counted at bytes / 3 like the gateway's estimate.
        tokens = _jev_tokens(body.get("state")) + sum(_jev_tokens(q) for q in (body.get("questions") or {}).values())
        cost = tokens * DECISION_COST_PER_M / 1e6
        gid = self._gen("dec", cost)
        return httpx.Response(200, json={"id": gid, "model": body.get("model"), "answers": answers,
                                         "usage": {"input_tokens": tokens, "output_tokens": 0, "cost": cost}})

    def _embed(self, body: dict[str, Any]) -> httpx.Response:
        inputs = body.get("input") or []
        dims = self.embed_dims or int(body.get("dimensions") or DEFAULT_DIMS)
        tokens = sum(_tokens(x) for x in inputs)
        cost = tokens * EMBED_COST_PER_M / 1e6
        gid = self._gen("gen", cost)
        return httpx.Response(200, json={
            "id": gid, "object": "list", "model": body.get("model"), "provider": "Nebius",
            "data": [{"object": "embedding", "index": i, "embedding": unit_vector(x, dims)} for i, x in enumerate(inputs)],
            "usage": {"prompt_tokens": tokens, "total_tokens": tokens, "cost": cost}})
