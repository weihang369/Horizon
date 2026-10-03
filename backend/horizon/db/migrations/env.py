"""Alembic environment. Migrations run on a plain (sync) sqlite3 connection; vec0 tables belong to the SpaceManager."""

from __future__ import annotations

import warnings
from typing import Any

from alembic import context
from sqlalchemy import create_engine, event

from horizon.db.migrate import include_object
from horizon.db.tables import metadata

config = context.config
# characters ↔ theme_songs/generation_jobs reference each other (SET NULL pointers); SQLite accepts forward FKs.
warnings.filterwarnings("ignore", message="Cannot correctly sort tables")


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection")
    if connectable is not None:
        _run(connectable)
        return
    engine = create_engine(config.get_main_option("sqlalchemy.url") or "")

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn: Any, _rec: Any) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=OFF")

    with engine.connect() as conn:
        _run(conn)
    engine.dispose()


def _run(conn: Any) -> None:
    context.configure(
        connection=conn,
        target_metadata=metadata,
        include_object=include_object,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
