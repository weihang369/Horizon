"""LangSmith tracing: forced off at every entry point, opt-in with a separate install (docs/ai/02 B11; NFR-13;
opt-in-tracing spec; ai-foundation design D30; task 6.5).

- `guard_env()` is the FIRST statement of `cli.main`, `main.create_app` and the pytest `conftest`. Unless
  `HORIZON_LANGSMITH=1`, it sets every LangSmith/LangChain tracing switch to `"false"` in `os.environ`, so a stray
  `LANGCHAIN_TRACING_V2=true` in a shell or `.env` can never send chat or document text anywhere.
- Opt-in needs `HORIZON_LANGSMITH=1`, `LANGSMITH_API_KEY` and the optional `tracing` dependency group (`langsmith`).
  `status()` says which is missing; start-up logs an error and stays untraced when any is.
- When on, `traced(name, inputs)` wraps a paid call in a LangSmith run whose inputs are the redacted call body
  (never headers, so never the OpenRouter key). `no_trace()` turns tracing off for a block (M9's graphs).
"""

from __future__ import annotations

import contextlib
import importlib.util
import logging
import os
from collections.abc import Iterator, Mapping
from typing import Any

from horizon.gateway.redact import redact as redact_key

log = logging.getLogger("horizon.tracing")

SWITCHES = ("LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING", "LANGCHAIN_TRACING")
OPT_IN = "HORIZON_LANGSMITH"
SECRET_KEYS = frozenset({"authorization", "api_key", "apikey", "key", "openrouter_key", "x-api-key"})


def opted_in(env: Mapping[str, str] | None = None) -> bool:
    return (env if env is not None else os.environ).get(OPT_IN, "").strip() in ("1", "true", "yes")


def guard_env(env: dict[str, str] | None = None) -> None:
    """Force tracing off unless the user opted in (D30). Idempotent; safe to call from every entry point."""
    target: Any = env if env is not None else os.environ
    if opted_in(target):
        return
    for name in SWITCHES:
        target[name] = "false"


def package_available() -> bool:
    return importlib.util.find_spec("langsmith") is not None


def status(env: Mapping[str, str] | None = None) -> tuple[bool, str]:
    """(enabled, reason) for the start-up line."""
    e = env if env is not None else os.environ
    if not opted_in(e):
        return False, "off"
    if not e.get("LANGSMITH_API_KEY"):
        return False, "HORIZON_LANGSMITH=1 but LANGSMITH_API_KEY is not set; tracing stays off"
    if not package_available():
        return False, "HORIZON_LANGSMITH=1 but the optional `tracing` group isn't installed (uv sync --group tracing)"
    return True, "on"


def startup_log(env: Mapping[str, str] | None = None) -> bool:
    on, reason = status(env)
    if on:
        log.warning("LangSmith tracing is ON: chat and document text in paid calls is sent to LangSmith (NFR-13 "
                    "exception you opted into)")
    elif reason != "off":
        log.error("%s", reason)
    else:
        log.info("LangSmith tracing off")
    return on


def switch_on(api_key: str, env: dict[str, str] | None = None) -> None:
    """The opt-in's side of `guard_env`. An opt-in from `.env` is read after `guard_env` ran, which already set every
    switch to "false", and langsmith reads `*_TRACING_V2` before `*_TRACING`: so all of them go back on (audit A-13)."""
    target: Any = env if env is not None else os.environ
    target["LANGSMITH_API_KEY"] = api_key   # langsmith reads it from the environment
    for name in SWITCHES:
        target[name] = "true"


def redact(value: Any) -> Any:
    """Drop anything that looks like a credential, at any depth; an `sk-or-` key inside any text is masked with the
    shared rule (local-backend "The API key never leaks", audit A-02)."""
    if isinstance(value, Mapping):
        return {k: redact(v) for k, v in value.items() if str(k).lower() not in SECRET_KEYS}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return redact_key(value)
    return value


class Tracer:
    """The process's tracer. `enabled` is decided once at start-up; `client` can be a stub in tests."""

    def __init__(self, enabled: bool = False, client: Any = None) -> None:
        self.enabled = enabled
        self.client = client

    @contextlib.contextmanager
    def traced(self, name: str, inputs: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
        """A run around one paid call; the caller fills `outputs`. Off: a plain dict and nothing sent."""
        outputs: dict[str, Any] = {}
        if not self.enabled:
            yield outputs
            return
        run_inputs = redact(dict(inputs))
        if self.client is not None:          # a stub in tests, or an injected client
            self.client.create_run(name=name, inputs=run_inputs, run_type="llm")
            try:
                yield outputs
            finally:
                self.client.end_run(name=name, outputs=redact(outputs))
            return
        from langsmith import trace  # the optional group; only reached when status() said it's installed

        with trace(name=name, run_type="llm", inputs=run_inputs) as run:
            yield outputs
            run.end(outputs=redact(outputs))


@contextlib.contextmanager
def no_trace() -> Iterator[None]:
    """Tracing off for a block (falls back to a null context without the package)."""
    if not package_available():
        yield
        return
    from langsmith import tracing_context

    with tracing_context(enabled=False):
        yield


TRACER = Tracer()


def configure(env: Mapping[str, str] | None = None) -> Tracer:
    TRACER.enabled = startup_log(env)
    return TRACER
