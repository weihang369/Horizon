"""Group A's shared harness (docs/ai/13-wrap-up.md W6, W10): the gateway's HTTP core, a hard spend cap, and the store.

- Requests go through `horizon.gateway.client.HttpCore` (the app's one outbound client) with the app's own chat body
  builder (`ChatClient.body`: the pinned routing block, `usage.include`, the fallback model). The key is read from the
  repo's `.env` by `load_config()` and never printed, logged or saved.
- **Spend cap:** every paid call is checked against `CAP_USD` across all group A runs (`data/cache/_spend/`), using a
  conservative estimate before sending and the provider's `usage.cost` after.
- **The store (W10):** `data/cache/<sha256>.json` = `{request, response, usage, savedAt}`, keyed by the SHA-256 of the
  canonical JSON of `{model, provider, parameters, body}` (+ the canary fingerprint for Jev entries). Latency and
  repeatability calls write to it but never read from it.

Run from `backend/`:  uv run python ../docs/ai/checks/group-a/run.py a1|a2|a3
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from horizon.config import REPO_ROOT, load_config
from horizon.gateway.chat import ChatClient, ChatRequest
from horizon.gateway.client import HttpCore
from horizon.gateway.errors import ProviderError
from horizon.gateway.types import GatewayConfig

HERE = Path(__file__).resolve().parent
OUT = HERE / "results"
CACHE = REPO_ROOT / "data" / "cache"
SPEND = CACHE / "_spend" / "group-a.jsonl"
CAP_USD = 0.30
PRICING = json.loads((REPO_ROOT / "seed" / "pricing.json").read_text(encoding="utf-8"))["data"]
JEV_MODEL = PRICING["decision"]["model"]
CHAT_MODEL = PRICING["chat"]["model"]
JEV_PATH = "/alpha/decisions"
CHAT_PATH = "/v1/chat/completions"


class CapReached(RuntimeError):
    pass


def canonical(o: Any) -> str:
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(o: Any) -> str:
    return hashlib.sha256(canonical(o).encode("utf-8")).hexdigest()


def est_tokens(o: Any) -> int:
    return len(canonical(o)) // 3 + 1   # conservative: real text runs ~4 chars a token


def pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    k = min(len(s) - 1, max(0, round(p / 100 * (len(s) - 1))))
    return s[k]


def dist(xs: list[float]) -> dict[str, Any]:
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "p50": pct(xs, 50), "p90": pct(xs, 90), "p99": pct(xs, 99), "max": max(xs),
            "mean": round(statistics.fmean(xs), 1)}


def write_json(name: str, obj: Any) -> Path:
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


class _Keys:
    """The KeySource HttpCore needs; holds the SecretStr only."""

    def __init__(self, key: SecretStr) -> None:
        self._key = key
        self._rejected = False

    def secret(self) -> SecretStr | None:
        return self._key

    def status(self) -> str:
        return "invalid" if self._rejected else "set"

    def mark_rejected(self, key: SecretStr) -> bool:
        self._rejected = True
        return True


class Harness:
    def __init__(self, check: str) -> None:
        cfg = load_config()
        if cfg.openrouter_key is None:
            sys.exit("No OpenRouter key: put OPENROUTER_API_KEY in the repo's .env (never paste it into chat).")
        self.check = check
        self.core = HttpCore(_Keys(cfg.openrouter_key))
        self.gcfg = GatewayConfig.from_mapping(PRICING["gateway"])
        self.chat = ChatClient(self.core, self.gcfg)
        self.fingerprint: str | None = None
        self.spent = 0.0
        if SPEND.exists():
            for line in SPEND.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self.spent += float(json.loads(line)["usd"])
        self.calls = 0
        self.hits = 0

    async def aclose(self) -> None:
        await self.core.aclose()

    # -- spend ------------------------------------------------------------------------------------------------------
    def _guard(self, estimate: float) -> None:
        if self.spent + estimate > CAP_USD:
            raise CapReached(f"cap ${CAP_USD:.2f} would be passed (spent ${self.spent:.4f}, next ≈ ${estimate:.4f})")

    def _log(self, kind: str, purpose: str, usd: float, *, estimated: bool) -> None:
        self.spent += usd
        self.calls += 1
        SPEND.parent.mkdir(parents=True, exist_ok=True)
        with SPEND.open("a", encoding="utf-8") as f:
            f.write(canonical({"at": dt.datetime.now(dt.UTC).isoformat(), "check": self.check, "kind": kind,
                               "purpose": purpose, "usd": usd, "estimated": estimated}) + "\n")

    async def key_usage(self) -> float | None:
        """The key's lifetime spend in USD (OpenRouter `/v1/key` → `usage`); only this number is read."""
        try:
            r = await self.core.request("GET", "/v1/key", http_timeout=10)
            u = (r.json().get("data") or {}).get("usage")
            return float(u) if isinstance(u, int | float) else None
        except (ProviderError, ValueError):
            return None

    # -- store ------------------------------------------------------------------------------------------------------
    @staticmethod
    def _path(key: str) -> Path:
        return CACHE / f"{key}.json"

    def _get(self, key: str) -> dict[str, Any] | None:
        p = self._path(key)
        if p.exists():
            self.hits += 1
            return json.loads(p.read_text(encoding="utf-8"))
        return None

    def _put(self, key: str, request: Any, response: Any, usage: Any) -> None:
        p = self._path(key)
        if p.exists():
            return  # the first answer stays (repeatability runs write the same key three times)
        CACHE.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(canonical({"request": request, "response": response, "usage": usage,
                                  "savedAt": dt.datetime.now(dt.UTC).isoformat()}), encoding="utf-8")
        tmp.replace(p)

    # -- Jev --------------------------------------------------------------------------------------------------------
    async def jev(self, state: Any, questions: dict[str, Any], *, purpose: str, use_store: bool = True,
                  timeout: float = 30.0) -> dict[str, Any]:
        body = {"model": JEV_MODEL, "state": state, "questions": questions}
        key_obj: dict[str, Any] = {"model": JEV_MODEL, "provider": "TypeSafe", "parameters": {},
                                   "body": {"state": state, "questions": questions}}
        if self.fingerprint:
            key_obj["canary"] = self.fingerprint
        key = sha(key_obj)
        if use_store and (hit := self._get(key)) is not None:
            r = hit["response"]
            return {"answers": r.get("answers", r.get("results")), "usage": hit["usage"], "ms": None, "cached": True,
                    "raw": r}
        price = PRICING["decision"]["inputPerM"] / 1e6
        estimate = est_tokens(state) * len(questions) * price + est_tokens(questions) * price  # worst case: per question
        self._guard(estimate)
        t0 = time.perf_counter()
        try:
            resp = await self.core.request("POST", JEV_PATH, json=body, http_timeout=timeout)
        except ProviderError as e:
            ms = (time.perf_counter() - t0) * 1000
            if e.maybe_charged:
                self._log("decision", purpose, estimate, estimated=True)
            return {"error": {"code": e.code, "status": e.status, "message": e.message}, "ms": round(ms, 1)}
        ms = (time.perf_counter() - t0) * 1000
        obj = resp.json()
        usage = obj.get("usage") or {}
        cost = usage.get("cost")
        self._log("decision", purpose, float(cost) if isinstance(cost, int | float) else estimate,
                  estimated=not isinstance(cost, int | float))
        self._put(key, {"state": state, "questions": questions}, obj, usage)
        return {"answers": obj.get("answers", obj.get("results")), "usage": usage, "ms": round(ms, 1), "cached": False,
                "raw": obj, "headers": {k: v for k, v in resp.headers.items()
                                        if k.lower() in ("x-generation-id", "server", "cf-ray", "x-request-id")}}

    async def jev_raw(self, state: Any, questions: dict[str, Any], *, purpose: str) -> dict[str, Any]:
        """One Jev request with the raw status, error body and rate-limit headers kept (the gateway's error mapping
        drops a 429's body). Uses HttpCore's own request builder, so the key handling is unchanged."""
        body = {"model": JEV_MODEL, "state": state, "questions": questions}
        price = PRICING["decision"]["inputPerM"] / 1e6
        estimate = (est_tokens(state) + est_tokens(questions)) * price
        self._guard(estimate)
        key = self.core._key()
        req = self.core._build("POST", JEV_PATH, key, json=body, timeout=60)
        t0 = time.perf_counter()
        resp = await self.core._client.send(req)
        ms = (time.perf_counter() - t0) * 1000
        text = resp.text
        heads = {k: v for k, v in resp.headers.items() if "limit" in k.lower() or "retry" in k.lower()}
        if resp.status_code == 200:
            obj = resp.json()
            usage = obj.get("usage") or {}
            self._log("decision", purpose, float(usage.get("cost") or estimate), estimated=usage.get("cost") is None)
            return {"status": 200, "ms": round(ms, 1), "usage": usage, "answers": obj.get("answers"), "headers": heads}
        return {"status": resp.status_code, "ms": round(ms, 1), "body": text[:600], "headers": heads}

    # -- chat -------------------------------------------------------------------------------------------------------
    def _chat_estimate(self, req: ChatRequest) -> float:
        p = PRICING["chat"]
        return (est_tokens(req.messages) * p["inputPerM"] + req.max_tokens * p["outputPerM"]) / 1e6 * 2  # ×2: peak

    def _chat_key(self, body: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        params = {k: v for k, v in body.items() if k not in ("messages", "model", "provider", "stream")}
        obj = {"model": body["model"], "provider": body.get("provider"), "parameters": params,
               "body": {"messages": body["messages"]}}
        return sha(obj), obj

    async def chat_complete(self, req: ChatRequest, *, purpose: str, use_store: bool = True) -> dict[str, Any]:
        body = self.chat.body(req, stream=False)
        key, key_obj = self._chat_key(body)
        if use_store and (hit := self._get(key)) is not None:
            return {"raw": hit["response"], "usage": hit["usage"], "ms": None, "cached": True}
        estimate = self._chat_estimate(req)
        self._guard(estimate)
        t0 = time.perf_counter()
        try:
            resp = await self.core.request("POST", CHAT_PATH, json=body, http_timeout=120)
        except ProviderError as e:
            if e.maybe_charged:
                self._log("chat", purpose, estimate, estimated=True)
            return {"error": {"code": e.code, "status": e.status, "message": e.message}}
        ms = (time.perf_counter() - t0) * 1000
        obj = resp.json()
        usage = obj.get("usage") or {}
        cost = usage.get("cost")
        self._log("chat", purpose, float(cost) if isinstance(cost, int | float) else estimate,
                  estimated=not isinstance(cost, int | float))
        self._put(key, key_obj, obj, usage)
        return {"raw": obj, "usage": usage, "ms": round(ms, 1), "cached": False}

    async def chat_stream_timed(self, req: ChatRequest, *, purpose: str) -> dict[str, Any]:
        """A streamed call read to the end (max_tokens kept small): time to the first content, provider, usage,
        and whether any reasoning deltas arrived. Never served from the store (latency)."""
        body = self.chat.body(req, stream=True)
        estimate = self._chat_estimate(req)
        self._guard(estimate)
        t0 = time.perf_counter()
        first_ms: float | None = None
        provider = gid = finish = None
        usage: dict[str, Any] = {}
        text: list[str] = []
        reasoning_chunks = 0
        try:
            async with self.core.stream("POST", CHAT_PATH, json=body, http_timeout=60) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    obj = json.loads(data)
                    gid = gid or obj.get("id")
                    provider = obj.get("provider") or provider
                    ch = (obj.get("choices") or [{}])[0]
                    delta = ch.get("delta") or {}
                    if delta.get("reasoning") or delta.get("reasoning_details"):
                        reasoning_chunks += 1
                    if delta.get("content"):
                        if first_ms is None:
                            first_ms = (time.perf_counter() - t0) * 1000
                        text.append(delta["content"])
                    finish = ch.get("finish_reason") or finish
                    if isinstance(obj.get("usage"), dict):
                        usage = obj["usage"]
        except ProviderError as e:
            self._log("chat", purpose, estimate, estimated=True)
            return {"error": {"code": e.code, "status": e.status, "message": e.message}}
        total_ms = (time.perf_counter() - t0) * 1000
        cost = usage.get("cost")
        self._log("chat", purpose, float(cost) if isinstance(cost, int | float) else estimate,
                  estimated=not isinstance(cost, int | float))
        return {"first_ms": round(first_ms, 1) if first_ms is not None else None, "total_ms": round(total_ms, 1),
                "provider": provider, "finish": finish, "usage": usage, "reasoning_chunks": reasoning_chunks,
                "text": "".join(text), "gid": gid}
