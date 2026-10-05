"""Process configuration (doc 01 §5).

Precedence for every setting: environment > `.env` (repo root) > `data/settings.local.json` > `seed/settings.json`.
This module owns the process-level values (paths, time zone, test mode, bind address). The UI-editable `AppSettings`
layering (local JSON over seed JSON) lives in `services/settings.py`.

The OpenRouter key (M2, doc 01 §5) is read from the environment, then `.env`, into a `SecretStr`; `data/secrets.local.json`
is the fallback, owned by `services/keys.py`. Test mode never reads a key from either (openrouter-key spec), so a
developer's real key can't leak into a test run or make a live call.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values
from pydantic import SecretStr

REPO_ROOT = Path(__file__).resolve().parents[2]
LOOPBACK = "127.0.0.1"
DEFAULT_PORT = 8000

# Process variables this module reads. An empty value counts as unset (`.env.example` ships blanks).
AI_VARS = ("HORIZON_AI_PROFILE", "HORIZON_AI_TURN", "HORIZON_AI_ROUTER", "HORIZON_AI_REACTIONS", "HORIZON_AI_HOST",
           "HORIZON_AI_DIRECTOR", "HORIZON_AI_SUMMARISER", "HORIZON_AI_GUARDRAIL")  # M3 (doc 05 §1)
KNOWN_VARS = (
    "HORIZON_ROOT", "HORIZON_DATA_DIR", "HORIZON_SEED_DIR", "HORIZON_TZ", "HORIZON_TEST", "HORIZON_PORT",
    "HORIZON_LOG_LEVEL", "HORIZON_STATIC_DIR", "OPENROUTER_API_KEY", *AI_VARS,
)


def _layered_env(root: Path, environ: dict[str, str] | None) -> dict[str, str]:
    env = dict(os.environ) if environ is None else dict(environ)
    dot = root / ".env"
    file_vals = {k: v for k, v in dotenv_values(dot).items() if v is not None} if dot.is_file() else {}
    merged: dict[str, str] = {}
    for k in KNOWN_VARS:
        if env.get(k, "").strip():
            merged[k] = env[k].strip()
        elif file_vals.get(k, "").strip():
            merged[k] = file_vals[k].strip()
    return merged


@dataclass(frozen=True)
class Config:
    repo_root: Path
    data_dir: Path
    seed_dir: Path
    tz: str = "Asia/Kuala_Lumpur"
    test_mode: bool = False
    port: int = DEFAULT_PORT
    log_level: str = "INFO"
    static_dir: Path | None = None
    # From OPENROUTER_API_KEY (env > .env). Always None in test mode. SecretStr: repr/str never show it.
    openrouter_key: SecretStr | None = None
    extra: dict[str, str] = field(default_factory=dict)
    ai_env: dict[str, str] = field(default_factory=dict)   # HORIZON_AI_PROFILE and the per-port overrides

    def __post_init__(self) -> None:
        if self.test_mode and self.openrouter_key is not None:  # holds for CLI/test overrides too
            object.__setattr__(self, "openrouter_key", None)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "horizon.db"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def assets_dir(self) -> Path:
        return self.data_dir / "assets"

    @property
    def settings_local_path(self) -> Path:
        return self.data_dir / "settings.local.json"

    @property
    def mock_seed_dir(self) -> Path:
        return self.seed_dir / "_mock"

    @property
    def schema_path(self) -> Path:
        return Path(__file__).resolve().parent / "contract" / "schema.json"


def load_config(environ: dict[str, str] | None = None, **overrides: object) -> Config:
    """Build the Config from the environment (and `.env`). `overrides` win over both (tests, CLI flags)."""
    root_hint = (environ if environ is not None else os.environ).get("HORIZON_ROOT")
    root = Path(root_hint).resolve() if root_hint else REPO_ROOT
    env = _layered_env(root, environ)
    data_dir = Path(env["HORIZON_DATA_DIR"]).resolve() if "HORIZON_DATA_DIR" in env else root / "data"
    seed_dir = Path(env["HORIZON_SEED_DIR"]).resolve() if "HORIZON_SEED_DIR" in env else root / "seed"
    static = env.get("HORIZON_STATIC_DIR")
    test_mode = env.get("HORIZON_TEST") == "1"
    key = env.get("OPENROUTER_API_KEY")
    values: dict[str, object] = {
        "repo_root": root,
        "data_dir": data_dir,
        "seed_dir": seed_dir,
        "tz": env.get("HORIZON_TZ", "Asia/Kuala_Lumpur"),
        "test_mode": test_mode,
        "port": int(env.get("HORIZON_PORT", DEFAULT_PORT)),
        "log_level": env.get("HORIZON_LOG_LEVEL", "INFO").upper(),
        "static_dir": Path(static).resolve() if static else None,
        "openrouter_key": SecretStr(key) if key and not test_mode else None,
        "ai_env": {k: env[k] for k in AI_VARS if k in env},
    }
    values.update(overrides)
    return Config(**values)  # type: ignore[arg-type]
