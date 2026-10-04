"""Scaffold (tasks 2.1–2.4): CLI loopback rule, config precedence, key redaction, the Clock and ids."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from horizon import cli
from horizon.config import load_config
from horizon.domain.clock import FrozenClock, calendar_for
from horizon.domain.ids import has_prefix, new_id
from horizon.logs import close_file_logging, setup_logging
from horizon.services.settings import deep_merge, read_local_settings, read_seed_settings

SEED = Path(__file__).resolve().parents[2].parent / "seed"


# ── 2.1 CLI ──
def test_serve_refuses_non_loopback(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["serve", "--host", "0.0.0.0"]) == 2
    assert "local-only" in capsys.readouterr().err


def test_factory_reset_needs_yes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HORIZON_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    marker = tmp_path / "data" / "keep.txt"
    marker.write_text("x")
    assert cli.main(["reset", "--factory"]) == 2
    assert marker.exists()


def test_export_schema_check_passes() -> None:
    assert cli.main(["export-schema", "--check"]) == 0


# ── 2.2 config precedence ──
def test_env_beats_dotenv(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("HORIZON_TZ=Europe/London\nHORIZON_PORT=9100\n", encoding="utf-8")
    cfg = load_config(environ={"HORIZON_ROOT": str(tmp_path), "HORIZON_TZ": "Asia/Tokyo"})
    assert cfg.tz == "Asia/Tokyo"  # environment wins
    assert cfg.port == 9100  # .env fills what the environment doesn't set
    assert cfg.data_dir == tmp_path / "data"


def test_local_settings_override_seed(tmp_path: Path) -> None:
    local = tmp_path / "settings.local.json"
    local.write_text(json.dumps({"audio": {"music": 0.2}}), encoding="utf-8")
    merged = deep_merge(read_seed_settings(SEED), read_local_settings(local))
    assert merged["audio"]["music"] == 0.2
    assert merged["audio"]["master"] == read_seed_settings(SEED)["audio"]["master"]


# ── M2 task 2.2: the key from env/.env (openrouter-key "Key sources", "Test mode ignores real keys") ──
def test_key_env_wins_over_dotenv(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=sk-or-test-dotenv\n", encoding="utf-8")
    cfg = load_config(environ={"HORIZON_ROOT": str(tmp_path), "OPENROUTER_API_KEY": "sk-or-test-env"})
    assert cfg.openrouter_key is not None
    assert cfg.openrouter_key.get_secret_value() == "sk-or-test-env"


def test_key_from_dotenv_and_blank_is_unset(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=sk-or-test-dotenv\nHORIZON_DATA_DIR=\n", encoding="utf-8")
    cfg = load_config(environ={"HORIZON_ROOT": str(tmp_path)})
    assert cfg.openrouter_key is not None and cfg.openrouter_key.get_secret_value() == "sk-or-test-dotenv"
    assert cfg.data_dir == tmp_path.resolve() / "data"  # a blank value is unset, never the cwd
    blank = load_config(environ={"HORIZON_ROOT": str(tmp_path), "OPENROUTER_API_KEY": "  "})
    assert blank.openrouter_key is not None  # a blank env value falls through to .env
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=\n", encoding="utf-8")
    assert load_config(environ={"HORIZON_ROOT": str(tmp_path)}).openrouter_key is None


def test_test_mode_ignores_every_key_source(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=sk-or-test-dotenv\n", encoding="utf-8")
    env = {"HORIZON_ROOT": str(tmp_path), "OPENROUTER_API_KEY": "sk-or-test-env", "HORIZON_TEST": "1"}
    assert load_config(environ=env).openrouter_key is None
    plain = {"HORIZON_ROOT": str(tmp_path)}
    assert load_config(environ=plain, test_mode=True).openrouter_key is None  # an override can't sneak one in


def test_key_never_shows_in_repr(tmp_path: Path) -> None:
    cfg = load_config(environ={"HORIZON_ROOT": str(tmp_path), "OPENROUTER_API_KEY": "sk-or-test-secret0001"})
    assert "sk-or" not in repr(cfg)
    assert "sk-or" not in str(cfg.openrouter_key) and "sk-or" not in f"{cfg.openrouter_key}"


# ── 2.3 logging ──
def test_key_is_redacted_everywhere(tmp_path: Path) -> None:
    setup_logging(tmp_path / "logs")
    log = logging.getLogger("horizon.test")
    try:
        raise ValueError("boom sk-or-v1-exc999")
    except ValueError:
        log.exception("failed with %s", "sk-or-v1-arg123")
    log.info("plain sk-or-v1-abc123 in the message")
    close_file_logging()
    text = (tmp_path / "logs" / "horizon.log").read_text(encoding="utf-8")
    assert "sk-or-v1" not in text
    assert text.count("sk-or-***") >= 3
    for line in text.splitlines():
        json.loads(line)


# ── 2.4 clock and ids ──
CAL = calendar_for("Asia/Kuala_Lumpur")


def _at(local: str) -> datetime:
    return datetime.fromisoformat(local + "+08:00").astimezone(UTC)


@pytest.mark.parametrize(("local", "period", "next_local"), [
    ("2026-10-06T10:00:00", "peak", "2026-10-06T12:00:00"),      # Tuesday 10:00
    ("2026-10-06T12:00:00", "off_peak", "2026-10-06T14:00:00"),  # 12:00 edge
    ("2026-10-06T17:59:00", "peak", "2026-10-06T18:00:00"),
    ("2026-10-06T18:00:00", "off_peak", "2026-10-07T09:00:00"),
    ("2026-10-03T11:00:00", "off_peak", "2026-10-05T09:00:00"),  # Saturday → Monday
])
def test_pricing_period(local: str, period: str, next_local: str) -> None:
    clock = FrozenClock(CAL, _at(local))
    assert clock.pricing_period() == period
    assert clock.next_change_at() == _at(next_local)


async def test_frozen_sleep_waits_for_virtual_time() -> None:
    """Session-runtime D2: a frozen sleep waits until an advance passes its deadline (time never moves by itself)."""
    import asyncio

    clock = FrozenClock(CAL, _at("2026-10-03T11:00:00"))
    woke: list[str] = []

    async def sleeper() -> None:
        await clock.sleep(90)
        woke.append(clock.now().isoformat())

    task = clock.activity.spawn("sleeper", sleeper())
    await clock.settle()
    assert woke == [] and clock.now() == _at("2026-10-03T11:00:00")
    await clock.advance(89_000)
    assert woke == []
    await clock.advance(1_000)
    assert woke == [_at("2026-10-03T11:01:30").isoformat()]
    await asyncio.wait_for(task, 1)


def test_ids_match_the_contract() -> None:
    for prefix in ("wld", "chr", "ses", "evt", "kno", "kch", "ksec", "cmd"):
        assert has_prefix(new_id(prefix), prefix)
    with pytest.raises(ValueError):
        new_id("xyz")
