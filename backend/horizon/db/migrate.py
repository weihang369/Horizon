"""Apply Alembic migrations (`upgrade head`). Runs on a plain sqlite3 connection; the app calls it in a thread."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config as AlembicConfig

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
SCRIPT_DIR = Path(__file__).resolve().parent / "migrations"


def alembic_config(db_path: Path) -> AlembicConfig:
    cfg = AlembicConfig(str(ALEMBIC_INI)) if ALEMBIC_INI.is_file() else AlembicConfig()
    cfg.set_main_option("script_location", str(SCRIPT_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    return cfg


def upgrade_head(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(alembic_config(db_path), "head")


def include_object(obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any) -> bool:
    """Skip FTS5/vec0 virtual tables and their shadow tables (doc 02 §3.9)."""
    return not (type_ == "table" and name is not None and ("_fts" in name or "_vec__" in name))
