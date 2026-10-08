"""`horizon models fetch` (knowledge-memory-storage task 5.3; document-conversion "Models are fetched once,
explicitly"; local-backend "Models fetch before setup")."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from horizon import cli
from horizon.ai import converter as cv


def docling_present(monkeypatch: pytest.MonkeyPatch, present: bool) -> None:
    real = importlib.util.find_spec

    def fake(name: str, *a: Any) -> Any:
        if name == "docling":
            return object() if present else None
        return real(name, *a)

    monkeypatch.setattr(importlib.util, "find_spec", fake)


def test_before_setup_it_names_the_step_and_downloads_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                              capsys: pytest.CaptureFixture[str]) -> None:
    docling_present(monkeypatch, False)
    monkeypatch.setenv("HORIZON_DATA_DIR", str(tmp_path / "data"))
    assert cli.main(["models", "fetch"]) == 2
    assert "npm run setup:docling" in capsys.readouterr().err
    assert not (tmp_path / "data" / "models").exists()


def test_a_completed_fetch_writes_the_marker_last(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    docling_present(monkeypatch, True)
    models = tmp_path / "models"
    seen: list[bool] = []

    def download(d: Path) -> None:
        seen.append((d / cv.MODELS_MARKER).exists())
        (d / "layout.safetensors").write_bytes(b"weights")

    cv.fetch_models(models, download=download)
    assert seen == [False] and (models / cv.MODELS_MARKER).is_file()
    assert cv.readiness(models) == "ready"


def test_an_interrupted_fetch_leaves_models_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    docling_present(monkeypatch, True)
    models = tmp_path / "models"
    models.mkdir()
    (models / cv.MODELS_MARKER).write_text("{}")   # an earlier fetch: a re-fetch must not keep claiming ready

    def download(d: Path) -> None:
        (d / "layout.partial").write_bytes(b"half")
        raise ConnectionError("network dropped")

    with pytest.raises(ConnectionError):
        cv.fetch_models(models, download=download)
    assert cv.readiness(models) == "models_missing"


def test_cli_reports_a_failed_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                       capsys: pytest.CaptureFixture[str]) -> None:
    docling_present(monkeypatch, True)
    monkeypatch.setenv("HORIZON_DATA_DIR", str(tmp_path / "data"))

    def download(_d: Path) -> None:
        raise ConnectionError("network dropped")

    monkeypatch.setattr(cv, "download_docling_models", download)
    monkeypatch.setattr(cv.fetch_models, "__kwdefaults__", {"download": download})
    assert cli.main(["models", "fetch"]) == 1
    assert "run it again" in capsys.readouterr().err
