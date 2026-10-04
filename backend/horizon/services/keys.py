"""The OpenRouter key (openrouter-key spec, doc 01 §5, doc 04 §5, design D3).

Sources, first wins: `OPENROUTER_API_KEY` (env > `.env`, read by `config.py`; never in test mode), then
`data/secrets.local.json` (`{"openRouterKey": "…"}`, written only by `PUT /settings/key`).

Status: `missing` (no key) · `invalid` (OpenRouter answered 401 for THIS key; remembered in memory by fingerprint until
the key changes or the backend restarts, OQ-K) · `set` otherwise. `demoMode` is `status != "set"`.

The key leaves its `SecretStr` only in `gateway/client.py`, for the `Authorization` header.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import SecretStr

from horizon.api.errors import conflict, validation

log = logging.getLogger("horizon.keys")

KeyStatus = Literal["missing", "set", "invalid"]
KeySource = Literal["env", "file"]

KEY_FORMAT = re.compile(r"^sk-or-[A-Za-z0-9_\-]+$")
SECRETS_FILE = "secrets.local.json"


def fingerprint(key: SecretStr) -> str:
    return hashlib.sha256(key.get_secret_value().encode("utf-8")).hexdigest()[:16]


def write_json_atomic(path: Path, data: object) -> None:
    """Write next to the target, then `os.replace` (atomic on Windows and POSIX when the target isn't held open)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class KeyStore:
    def __init__(self, env_key: SecretStr | None, data_dir: Path, *, on_change: Callable[[], None] | None = None) -> None:
        self._env_key = env_key
        self.path = data_dir / SECRETS_FILE
        self._file_key = self._read_file()
        self._rejected: str | None = None
        self.on_change = on_change

    # ── reading ──
    def _read_file(self) -> SecretStr | None:
        if not self.path.is_file():
            return None
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.warning("ignoring unreadable %s", SECRETS_FILE)  # never log the content
            return None
        raw = doc.get("openRouterKey") if isinstance(doc, dict) else None
        if isinstance(raw, str) and KEY_FORMAT.match(raw.strip()):
            return SecretStr(raw.strip())
        log.warning("ignoring %s: no well-formed openRouterKey", SECRETS_FILE)
        return None

    def effective(self) -> tuple[SecretStr, KeySource] | None:
        if self._env_key is not None:
            return self._env_key, "env"
        if self._file_key is not None:
            return self._file_key, "file"
        return None

    def secret(self) -> SecretStr | None:
        eff = self.effective()
        return eff[0] if eff else None

    def status(self) -> KeyStatus:
        key = self.secret()
        if key is None:
            return "missing"
        return "invalid" if self._rejected == fingerprint(key) else "set"

    def demo_mode(self) -> bool:
        return self.status() != "set"

    # ── writing ──
    def set_key(self, key: str | None) -> None:
        """PUT /settings/key: format check only, no network. `None` deletes the secrets file."""
        eff = self.effective()
        if eff is not None and eff[1] == "env":
            raise conflict("The key is set by OPENROUTER_API_KEY in the environment or .env; change it there.",
                           {"field": "key", "source": "env"})
        if key is None:
            self.path.unlink(missing_ok=True)
            self._file_key = None
        else:
            k = key.strip()
            if not KEY_FORMAT.match(k):
                raise validation("OpenRouter keys start with sk-or- followed by letters, digits, - or _.",
                                 {"field": "key"})
            write_json_atomic(self.path, {"openRouterKey": k})
            self._file_key = SecretStr(k)
        self._rejected = None
        self._changed()

    def mark_rejected(self, key: SecretStr) -> bool:
        """A 401 for `key`. Returns True when that flipped the status (the caller's event is then due)."""
        current = self.secret()
        if current is None or fingerprint(current) != fingerprint(key) or self._rejected == fingerprint(key):
            return False
        self._rejected = fingerprint(key)
        self._changed()
        return True

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()
