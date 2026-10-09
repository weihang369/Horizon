"""`.env.example` documents every variable the config reads, with no key in it (local-backend "Committed environment
template"; http-client-parity D17, task 5.1). Same pattern as M5's `set(AI_VARS) == set(profile.ENV_VARS)`."""

from __future__ import annotations

import re
from pathlib import Path

from horizon.config import KNOWN_VARS, REPO_ROOT

TEMPLATE = REPO_ROOT / ".env.example"
LINE = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]*)=(.*)$")
KEY_TOKEN = re.compile(r"sk-or-[A-Za-z0-9_-]+")


def documented(path: Path) -> dict[str, str]:
    """Each `NAME=value` or commented `# NAME=value` line, by name."""
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = LINE.match(line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def missing(known: tuple[str, ...], path: Path) -> list[str]:
    names = documented(path)
    return [k for k in known if k not in names]


def test_every_config_variable_is_documented() -> None:
    assert missing(KNOWN_VARS, TEMPLATE) == []


def test_the_check_names_an_undocumented_variable() -> None:
    assert missing((*KNOWN_VARS, "HORIZON_NOT_DOCUMENTED"), TEMPLATE) == ["HORIZON_NOT_DOCUMENTED"]


def test_the_key_is_blank_and_no_key_shaped_text_exists() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    assert documented(TEMPLATE)["OPENROUTER_API_KEY"] == ""
    assert re.search(r"^OPENROUTER_API_KEY=$", text, re.M)
    assert KEY_TOKEN.search(text) is None


def test_env_is_git_ignored() -> None:
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in [line.strip() for line in ignored]
