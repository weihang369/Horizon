"""KeyStore (task 2.3): the openrouter-key spec scenarios that don't need HTTP. Only fake `sk-or-test-…` keys."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from pydantic import SecretStr

from horizon.api.errors import HorizonHTTPError
from horizon.services.keys import KeyStore


def store(tmp_path: Path, env: str | None = None) -> tuple[KeyStore, list[str]]:
    seen: list[str] = []
    ks = KeyStore(SecretStr(env) if env else None, tmp_path, on_change=lambda: seen.append("changed"))
    return ks, seen


def test_no_key_is_missing_and_demo(tmp_path: Path) -> None:
    ks, _ = store(tmp_path)
    assert ks.status() == "missing" and ks.demo_mode() and ks.secret() is None


def test_save_key_writes_file_and_sets(tmp_path: Path) -> None:
    ks, seen = store(tmp_path)
    ks.set_key("  sk-or-test-0001 ")
    assert ks.status() == "set" and not ks.demo_mode()
    assert json.loads((tmp_path / "secrets.local.json").read_text(encoding="utf-8")) == {"openRouterKey": "sk-or-test-0001"}
    assert seen == ["changed"]
    assert KeyStore(None, tmp_path).status() == "set"  # survives a restart
    assert not list(tmp_path.glob("*.tmp"))  # the atomic write left nothing behind


@pytest.mark.parametrize("bad", ["hello", "sk-or-", "sk-or-has space", "sk-ant-test-0001", ""])
def test_malformed_key_is_validation_and_changes_nothing(tmp_path: Path, bad: str) -> None:
    ks, seen = store(tmp_path)
    ks.set_key("sk-or-test-0001")
    with pytest.raises(HorizonHTTPError) as e:
        ks.set_key(bad)
    assert e.value.code == "validation" and e.value.details == {"field": "key"}
    assert ks.secret() is not None and ks.secret().get_secret_value() == "sk-or-test-0001"  # type: ignore[union-attr]
    assert seen == ["changed"]


def test_clear_key_deletes_file(tmp_path: Path) -> None:
    ks, _ = store(tmp_path)
    ks.set_key("sk-or-test-0001")
    ks.set_key(None)
    assert not (tmp_path / "secrets.local.json").exists()
    assert ks.status() == "missing" and ks.demo_mode()


def test_env_key_wins_and_blocks_ui_writes(tmp_path: Path) -> None:
    (tmp_path / "secrets.local.json").write_text('{"openRouterKey": "sk-or-test-file"}', encoding="utf-8")
    ks, seen = store(tmp_path, env="sk-or-test-env")
    assert ks.effective() is not None and ks.effective()[1] == "env"  # type: ignore[index]
    for attempt in ("sk-or-test-other", None):
        with pytest.raises(HorizonHTTPError) as e:
            ks.set_key(attempt)
        assert e.value.code == "conflict" and e.value.details == {"field": "key", "source": "env"}
    assert json.loads((tmp_path / "secrets.local.json").read_text(encoding="utf-8"))["openRouterKey"] == "sk-or-test-file"
    assert seen == []


def test_401_flips_to_invalid_until_the_key_changes(tmp_path: Path) -> None:
    ks, seen = store(tmp_path)
    ks.set_key("sk-or-test-0001")
    key = ks.secret()
    assert key is not None
    assert ks.mark_rejected(key) is True
    assert ks.status() == "invalid" and ks.demo_mode()
    assert ks.mark_rejected(key) is False  # already invalid: no second event
    assert ks.mark_rejected(SecretStr("sk-or-test-stale")) is False  # a stale key's 401 says nothing about this one
    ks.set_key("sk-or-test-0002")
    assert ks.status() == "set"
    assert seen == ["changed", "changed", "changed"]
    assert KeyStore(None, tmp_path).status() == "set"  # invalid is in memory only (OQ-K)


def test_unreadable_file_is_ignored_without_logging_it(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    (tmp_path / "secrets.local.json").write_text("{not json sk-or-test-0001", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        ks, _ = store(tmp_path)
    assert ks.status() == "missing"
    assert "sk-or-test" not in caplog.text
