"""The shared response store (docs/ai/13 W10; docs/ai/02 B7; ai-foundation design D31, D35; tasks 7.1, 7.2).

One paid answer is reused by every later check, evaluation and demo run that sends the same request ("pay once"):
- an entry is `data/cache/<key>.json` = `{request, response, usage, savedAt}` (group A's format, so its 300+ recorded
  answers are already hits);
- `key = sha256(canonical({model, provider, parameters, body} [+ canary]))` with group A's `canonical()`:

  | kind       | provider             | parameters                                      | body                  |
  |------------|----------------------|-------------------------------------------------|-----------------------|
  | chat       | the routing block    | the body minus messages/model/provider/stream   | `{messages}`          |
  | jev        | "TypeSafe"           | `{}`                                            | `{state, questions}` + `canary` |
  (the canary is the fingerprint of the asked model's own accepted baseline; jev-comparison D5)
  | embeddings | the routing block    | `{dimensions}`                                  | `{input}`             |

- writes are atomic (tmp → fsync → replace) and the first write wins;
- a hit sends nothing, reserves nothing and writes no ledger row (nothing was spent).

**Views** (W10): the *eval* view serves chat, Jev and embeddings, and only `horizon eval` runs attach it to their
isolated runtime. The *seed* view serves embeddings only, and the live app passes it only where the caller says the
input is shipped seed text (`store_ok=True`: seed knowledge and seed memories). User text never goes through it.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Kind = Literal["chat", "jev", "embeddings"]
EVAL_KINDS: frozenset[Kind] = frozenset({"chat", "jev", "embeddings"})
SEED_KINDS: frozenset[Kind] = frozenset({"embeddings"})


def canonical(o: Any) -> str:
    """Group A's canonical JSON (docs/ai/checks/group-a/harness.py): sorted keys, no spaces, UTF-8 kept."""
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(o: Any) -> str:
    return hashlib.sha256(canonical(o).encode("utf-8")).hexdigest()


def jev_key(model: str, state: Any, questions: Mapping[str, Any], fingerprint: str | None,
            order: Mapping[str, list[str]] | None = None) -> str:
    """M15 (images-music D13): a choice's options are a mapping, so `canonical()` loses their order. A caller asking
    with an order other than the declared one (the decisions suite's reversed ask) passes `order` = {question id:
    option ids}, which salts the key. Declared-order requests pass nothing and keep their old key."""
    obj: dict[str, Any] = {"model": model, "provider": "TypeSafe", "parameters": {},
                           "body": {"state": state, "questions": questions}}
    if fingerprint:
        obj["canary"] = fingerprint
    if order:
        obj["order"] = {k: list(v) for k, v in order.items()}
    return sha(obj)


def chat_key(body: Mapping[str, Any]) -> str:
    params = {k: v for k, v in body.items() if k not in ("messages", "model", "provider", "stream")}
    return sha({"model": body["model"], "provider": body.get("provider"), "parameters": params,
                "body": {"messages": body["messages"]}})


def embeddings_key(body: Mapping[str, Any]) -> str:
    return sha({"model": body["model"], "provider": body.get("provider"),
                "parameters": {"dimensions": body.get("dimensions")}, "body": {"input": body["input"]}})


@dataclass
class ResponseStore:
    root: Path
    kinds: frozenset[Kind] = EVAL_KINDS
    fingerprint: str | None = None        # the accepted canary's; salts every Jev key (D32)
    hits: int = 0
    writes: int = 0
    probe: bool = False                   # M15 (images-music D13): a miss stops the call before anything is sent
    misses: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def eval_view(cls, root: Path, fingerprint: str | None) -> ResponseStore:
        return cls(root, EVAL_KINDS, fingerprint)

    @classmethod
    def seed_view(cls, root: Path) -> ResponseStore:
        return cls(root, SEED_KINDS)

    def serves(self, kind: Kind) -> bool:
        return kind in self.kinds

    def path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, kind: Kind, key: str) -> dict[str, Any] | None:
        if not self.serves(kind):
            return None
        p = self.path(key)
        try:
            entry: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        self.hits += 1
        return entry

    def miss(self, kind: Kind, key: str, estimate_usd: float) -> bool:
        """The gateway calls this after a lookup found nothing, before it reserves or sends. In a probe it records what
        the call would have cost and returns True: the gateway then sends nothing and answers empty (no Jev answers,
        an empty reply), so the caller's usual missing-answer path runs. Otherwise it returns False."""
        if not self.probe:
            return False
        self.misses.append({"kind": kind, "key": key, "usd": float(estimate_usd)})
        return True

    def put(self, kind: Kind, key: str, request: Any, response: Any, usage: Any) -> bool:
        """Atomic, and the first answer stays. Returns whether this call wrote the entry."""
        if not self.serves(kind):
            return False
        p = self.path(key)
        if p.exists():
            return False
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(f".{os.getpid()}.tmp")
        data = canonical({"request": request, "response": response, "usage": usage,
                          "savedAt": dt.datetime.now(dt.UTC).isoformat()})
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        try:
            if p.exists():          # another writer won the race: keep the first
                tmp.unlink(missing_ok=True)
                return False
            os.replace(tmp, p)
        except OSError:
            tmp.unlink(missing_ok=True)
            return False
        self.writes += 1
        return True

    def size(self) -> tuple[int, int]:
        """(entries, bytes) for `horizon stats`."""
        if not self.root.is_dir():
            return 0, 0
        files = [p for p in self.root.glob("*.json")]
        return len(files), sum(p.stat().st_size for p in files)
