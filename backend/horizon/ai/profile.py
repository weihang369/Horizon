"""AI profile selection (doc 05 §1; ai-ports "AI profile selection"; design OQ-3, OQ-14).

`HORIZON_AI_PROFILE` (`scripted` | `naive`) selects every port; without it the profile is `naive` when a key is set and
`scripted` otherwise. `HORIZON_AI_<PORT>` overrides one port. The turn engine, the router (M3), the profile drafter,
the image generator (M4) and the song generator (Lyria 3 Clip, D-87) have naive implementations; every other port is
scripted in both profiles. The scripted song is the free procedural theme (D-83). The creation port is called
`drafter`, not `profile`, because `HORIZON_AI_PROFILE` is the selector itself. In test mode, `POST /_test/ai-profile`
replaces the selection at runtime.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from horizon.ai.scripted.creation import ProceduralSong, ScriptedDrafter, ScriptedImageGenerator
from horizon.ai.scripted.ports import (
    AiDeps,
    ScriptedDebateHost,
    ScriptedGuardrail,
    ScriptedReactions,
    ScriptedRouter,
    ScriptedSummariser,
    ScriptedTurnEngine,
    ScriptedWatchDirector,
)

Impl = Literal["scripted", "naive"]
PORTS = ("turn", "router", "reactions", "host", "director", "summariser", "guardrail", "drafter", "image", "song")
NAIVE_PORTS = frozenset({"turn", "router", "drafter", "image", "song"})
ENV_PROFILE = "HORIZON_AI_PROFILE"


def env_name(port: str) -> str:
    return f"HORIZON_AI_{port.upper()}"


ENV_VARS = (ENV_PROFILE, *(env_name(p) for p in PORTS))


def _impl(value: str | None) -> Impl | None:
    v = (value or "").strip().lower()
    if v in ("scripted", "naive"):
        return v  # type: ignore[return-value]
    return None


@dataclass(frozen=True)
class ProfileSpec:
    profile: Impl | None = None
    overrides: Mapping[str, Impl] = field(default_factory=dict)

    @staticmethod
    def from_env(env: Mapping[str, str]) -> ProfileSpec:
        overrides: dict[str, Impl] = {}
        for p in PORTS:
            impl = _impl(env.get(env_name(p)))
            if impl is not None:
                overrides[p] = impl
        return ProfileSpec(profile=_impl(env.get(ENV_PROFILE)), overrides=overrides)

    def choose(self, port: str, *, key_set: bool) -> Impl:
        impl: Impl = self.overrides.get(port) or self.profile or ("naive" if key_set else "scripted")
        return impl if impl == "scripted" or port in NAIVE_PORTS else "scripted"


class AiPorts:
    """Resolves each port per call from the profile and the key status; instances are cached per implementation."""

    def __init__(self, deps: AiDeps, spec: ProfileSpec) -> None:
        self.deps = deps
        self.spec = spec
        self._cache: dict[tuple[str, str], Any] = {}

    def impl(self, port: str, *, key_set: bool) -> Impl:
        return self.spec.choose(port, key_set=key_set)

    def _get(self, port: str, key_set: bool) -> Any:
        impl = self.impl(port, key_set=key_set)
        k = (port, impl)
        if k not in self._cache:
            self._cache[k] = self._build(port, impl)
        return self._cache[k]

    def _build(self, port: str, impl: Impl) -> Any:
        d = self.deps
        if impl == "naive":
            if port == "turn":
                from horizon.ai.naive.turn import NaiveTurnEngine
                return NaiveTurnEngine(d)
            if port == "drafter":
                from horizon.ai.naive.creation import NaiveDrafter
                return NaiveDrafter(d, d.schema, d.palette_ids)
            if port == "song":
                from horizon.ai.naive.creation import NaiveSong
                return NaiveSong(d)
            if port == "image":
                from horizon.ai.naive.creation import NaiveImageGenerator
                return NaiveImageGenerator(d)
            from horizon.ai.naive.router import JevRouter
            return JevRouter(d)
        builders: dict[str, Callable[[], Any]] = {
            "turn": lambda: ScriptedTurnEngine(d), "router": lambda: ScriptedRouter(d),
            "reactions": lambda: ScriptedReactions(d), "host": lambda: ScriptedDebateHost(d),
            "director": lambda: ScriptedWatchDirector(), "summariser": lambda: ScriptedSummariser(d),
            "guardrail": lambda: ScriptedGuardrail(), "drafter": lambda: ScriptedDrafter(d, d.palette_ids),
            "image": lambda: ScriptedImageGenerator(d), "song": lambda: ProceduralSong()}
        return builders[port]()

    def turn(self, key_set: bool) -> Any:
        return self._get("turn", key_set)

    def router(self, key_set: bool) -> Any:
        return self._get("router", key_set)

    def reactions(self, key_set: bool) -> Any:
        return self._get("reactions", key_set)

    def host(self, key_set: bool) -> Any:
        return self._get("host", key_set)

    def director(self, key_set: bool) -> Any:
        return self._get("director", key_set)

    def summariser(self, key_set: bool) -> Any:
        return self._get("summariser", key_set)

    def guardrail(self, key_set: bool) -> Any:
        return self._get("guardrail", key_set)

    def drafter(self, key_set: bool) -> Any:
        return self._get("drafter", key_set)

    def image(self, key_set: bool) -> Any:
        return self._get("image", key_set)

    def song(self, key_set: bool) -> Any:
        return self._get("song", key_set)

    def override(self, port: str, impl: Any) -> None:
        """Tests: inject one port's implementation for both profiles (e.g. a blocking guardrail, design D13)."""
        self._cache[(port, "scripted")] = impl
        self._cache[(port, "naive")] = impl
