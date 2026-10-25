"""HttpCore (design D2, D6): the ONE outbound HTTP client, and the only place the key leaves its SecretStr.

- The transport is chosen once: the network normally, the in-process `FakeOpenRouter` in test mode, respx in unit
  tests. Request building and error mapping are the same code path in all three.
- The key guard runs before anything is sent: no key → `missing_key`; a key OpenRouter already rejected →
  `invalid_key` (mock parity: live actions refuse until the key changes).
- **Retry only when nothing can have been charged:** a connect failure (nothing sent), or a 429/5xx with an empty
  body. Once request bytes are on the wire and the read fails, the call is NOT retried; it surfaces as
  `maybe_charged` and the pipeline records it at its estimate.
- A 401 marks the key rejected (the status flips to `invalid`).
- **Warm connections (v1 test stage).** A fresh connection to OpenRouter costs 600-950 ms about one time in four from
  Malaysia (measured 2026-10-20: the IPv6 attempt stalls and happy eyeballs falls back to IPv4), against 30-60 ms
  for a reused one. httpx keeps idle connections only 5 s, so nearly every turn opened new ones and the first Jev call
  of a session missed its 700 ms deadline. So idle connections are kept for `KEEPALIVE_S`, and `warm()` opens a few
  (an unauthenticated GET of a public model page, no key sent) when a session is opened, before its first turn.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any, Protocol

import httpx
from pydantic import SecretStr

from horizon.gateway.errors import ProviderError, from_status

BASE_URL = "https://openrouter.ai/api"
RETRY_PAUSE_S = 0.25
KEEPALIVE_S = 300.0         # measured 2026-10-20: OpenRouter still reuses a connection idle for 240 s (47 ms)
WARM_CONNECTIONS = 3        # a turn's concurrent calls: Jev's turn plan, the reply stream, and a check
WARM_TIMEOUT_S = 5.0
WARM_EVERY_S = 30.0         # a session opened again within this window reuses the last warm-up
PURPOSE_HEADER = "X-Horizon-Purpose"
# The paid call being sent (set by the pipeline around a request). In test mode only, HttpCore labels the request with
# it, so the fake provider can answer per purpose with recorded responses (docs/ai/13 W14). Never sent to OpenRouter.
CALL_PURPOSE: contextvars.ContextVar[str | None] = contextvars.ContextVar("horizon_call_purpose", default=None)


class KeySource(Protocol):
    def secret(self) -> SecretStr | None: ...
    def status(self) -> str: ...
    def mark_rejected(self, key: SecretStr) -> bool: ...


class HttpCore:
    def __init__(self, keys: KeySource, *, transport: httpx.AsyncBaseTransport | None = None,
                 base_url: str = BASE_URL, label_purpose: bool = False) -> None:
        self.keys = keys
        self.label_purpose = label_purpose   # test mode only (W14): add the X-Horizon-Purpose header
        self._live = transport is None       # the fake provider, respx and the probe's deny transport are never warmed
        self._warmed_at = -WARM_EVERY_S
        self._client = httpx.AsyncClient(base_url=base_url, transport=transport,
                                         limits=httpx.Limits(max_keepalive_connections=8, keepalive_expiry=KEEPALIVE_S),
                                         headers={"X-Title": "Horizon", "HTTP-Referer": "http://127.0.0.1"})

    async def aclose(self) -> None:
        await self._client.aclose()

    async def warm(self, path: str) -> None:
        """Open `WARM_CONNECTIONS` pooled connections ahead of a turn. Only with a key (no key: the app stays offline),
        never in test or probe mode, at most once per `WARM_EVERY_S`; failures are ignored (a turn opens its own)."""
        now = asyncio.get_running_loop().time()
        if not self._live or self.keys.secret() is None or now - self._warmed_at < WARM_EVERY_S:
            return
        self._warmed_at = now

        async def one() -> None:
            with contextlib.suppress(httpx.HTTPError):
                await self._client.get(path, timeout=WARM_TIMEOUT_S)

        await asyncio.gather(*(one() for _ in range(WARM_CONNECTIONS)))

    def require_key(self) -> None:
        """The key guard alone (the pipeline runs it before the cap preflight, so no key reads as missing_key)."""
        self._key()

    def _key(self) -> SecretStr:
        key = self.keys.secret()
        if key is None:
            raise ProviderError("missing_key")
        if self.keys.status() == "invalid":
            raise ProviderError("invalid_key")
        return key

    def _build(self, method: str, path: str, key: SecretStr, *, json: Any = None,
               params: Mapping[str, str] | None = None, timeout: float) -> httpx.Request:
        req = self._client.build_request(method, path, json=json, params=params, timeout=httpx.Timeout(timeout))
        req.headers["Authorization"] = f"Bearer {key.get_secret_value()}"
        purpose = CALL_PURPOSE.get() if self.label_purpose else None
        if purpose:
            req.headers[PURPOSE_HEADER] = purpose
        return req

    async def _send(self, req: httpx.Request, key: SecretStr, *, stream: bool) -> httpx.Response:
        for attempt in (0, 1):
            try:
                resp = await self._client.send(req, stream=stream)
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                if attempt == 0:
                    await asyncio.sleep(RETRY_PAUSE_S)
                    continue
                raise ProviderError("provider_error", "Couldn't reach OpenRouter.") from e
            except httpx.PoolTimeout as e:  # never left the pool: nothing sent
                raise ProviderError("timeout") from e
            except httpx.TimeoutException as e:  # read/write timeout once sent: may have been charged
                raise ProviderError("timeout", maybe_charged=True) from e
            except httpx.TransportError as e:  # read error / protocol error after send
                raise ProviderError("provider_error", "The connection to OpenRouter broke.", maybe_charged=True) from e
            if resp.status_code < 400:
                return resp
            body = (await resp.aread()).decode("utf-8", "replace")
            await resp.aclose()
            if attempt == 0 and (resp.status_code == 429 or resp.status_code >= 500) and not body.strip():
                await asyncio.sleep(RETRY_PAUSE_S)
                continue
            if resp.status_code == 401:
                self.keys.mark_rejected(key)
            raise from_status(resp.status_code, body, resp.headers)
        raise AssertionError("unreachable")

    async def request(self, method: str, path: str, *, json: Any = None, params: Mapping[str, str] | None = None,
                      http_timeout: float) -> httpx.Response:
        """A complete (non-streaming) request. The body is read before returning."""
        key = self._key()
        resp = await self._send(self._build(method, path, key, json=json, params=params, timeout=http_timeout), key,
                                stream=False)
        return resp

    @asynccontextmanager
    async def stream(self, method: str, path: str, *, json: Any = None, http_timeout: float) -> AsyncIterator[httpx.Response]:
        """A streaming request: yields the open response; the caller iterates `aiter_lines()`."""
        key = self._key()
        resp = await self._send(self._build(method, path, key, json=json, timeout=http_timeout), key, stream=True)
        try:
            yield resp
        finally:
            await resp.aclose()
