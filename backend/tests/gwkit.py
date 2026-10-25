"""Test kit for the gateway: a fake key source, recorded OpenRouter fixtures and respx helpers. Fake keys only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from pydantic import SecretStr

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "openrouter"
TEST_KEY = "sk-or-test-0001"


class FakeKeys:
    """Duck-types the KeySource protocol without touching disk."""

    def __init__(self, key: str | None = TEST_KEY) -> None:
        self.key = SecretStr(key) if key else None
        self.rejected = False
        self.rejections = 0

    def secret(self) -> SecretStr | None:
        return self.key

    def status(self) -> str:
        if self.key is None:
            return "missing"
        return "invalid" if self.rejected else "set"

    def mark_rejected(self, key: SecretStr) -> bool:
        self.rejections += 1
        changed = not self.rejected
        self.rejected = True
        return changed


def load(name: str) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return doc


def response(name: str, **overrides: Any) -> httpx.Response:
    """An httpx.Response built from a recorded fixture (`body` = JSON, `sse` = event-stream lines)."""
    doc = {**load(name), **overrides}
    headers = dict(doc.get("headers") or {})
    if "sse" in doc:
        def frame(x: Any) -> str:
            if isinstance(x, str):  # ": comment" lines go out raw; other strings ([DONE]) as data
                return f"{x}\n\n" if x.startswith(":") else f"data: {x}\n\n"
            return f"data: {json.dumps(x)}\n\n"

        text = "".join(frame(x) for x in doc["sse"])
        headers.setdefault("content-type", "text/event-stream")
        return httpx.Response(doc.get("status", 200), headers=headers, content=text.encode("utf-8"))
    body = doc.get("body")
    if body is None:
        return httpx.Response(doc.get("status", 200), headers=headers, content=b"")
    return httpx.Response(doc.get("status", 200), headers=headers, json=body)


LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def block_network(monkeypatch: Any) -> list[str]:
    """Fail any outbound connection that isn't loopback (asyncio and the test servers use loopback). Returns the log."""
    import socket

    attempts: list[str] = []
    real_connect = socket.socket.connect
    real_create = socket.create_connection

    def host_of(address: Any) -> str:
        return str(address[0]) if isinstance(address, tuple) else str(address)

    def connect(self: socket.socket, address: Any) -> Any:
        if host_of(address) not in LOOPBACK:
            attempts.append(host_of(address))
            raise AssertionError(f"network access attempted: {host_of(address)}")
        return real_connect(self, address)

    def create_connection(address: Any, *a: Any, **k: Any) -> Any:
        if host_of(address) not in LOOPBACK:
            attempts.append(host_of(address))
            raise AssertionError(f"network access attempted: {host_of(address)}")
        return real_create(address, *a, **k)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "create_connection", create_connection)
    return attempts


SEED = Path(__file__).resolve().parents[2] / "seed"


def gateway_config(**timeouts_s: float) -> Any:
    """The committed gateway config, with some timeouts (in seconds) overridden for fast tests."""
    from dataclasses import replace

    from horizon.domain.pricing import load_price_table
    from horizon.gateway.types import GatewayConfig

    cfg = GatewayConfig.from_mapping(load_price_table(SEED).gateway)
    return replace(cfg, timeouts=replace(cfg.timeouts, **timeouts_s)) if timeouts_s else cfg


class SlowStream(httpx.AsyncByteStream):
    """An SSE body whose parts arrive after the given delays (seconds), for timeout tests."""

    def __init__(self, parts: list[tuple[float, str]]) -> None:
        self.parts = parts

    async def __aiter__(self) -> Any:
        import asyncio

        for delay, text in self.parts:
            await asyncio.sleep(delay)
            yield text.encode("utf-8")


def build_gateway(api: Any, *, keys: Any = None, caps: Any = None, transport: Any = None, events: list[Any] | None = None,
                  **kw: Any) -> Any:
    """A Gateway over the test runtime's real DB and clock, with respx (default transport) or a given transport."""
    from horizon.domain.timeutil import ms_from_iso, to_iso
    from horizon.gateway.client import HttpCore
    from horizon.gateway.pipeline import Caps, Gateway
    from horizon.gateway.reservations import ReservationBook
    from horizon.gateway.types import GatewayConfig
    from horizon.services.energy_writes import EnergyLocks, EnergyParams
    from horizon.services.ledger import LedgerWriter

    rt = api.rt
    sink = events if events is not None else []

    def params() -> EnergyParams:
        return EnergyParams(now_ms=ms_from_iso(to_iso(rt.clock.now())), frozen=False, est_reply_points=4,
                            usd_per_point=0.0001, utc_offset_min=480)

    ledger = LedgerWriter(rt.db, rt.clock, EnergyLocks(), params)
    return Gateway(core=HttpCore(keys or FakeKeys(), transport=transport), cfg=GatewayConfig.from_mapping(rt.prices.gateway),
                   prices=rt.prices, book=ReservationBook(), ledger=ledger,
                   caps=lambda: caps or Caps(daily_cap_usd=1.0, creation_cap_usd=0.6, warn_at_pct=80),
                   period=rt.clock.pricing_period, publish=sink.append, decision_model="typesafe/jev-1.13", **kw)
